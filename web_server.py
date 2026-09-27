"""Local, dependency-free web UI for the extracted ThePiper toolkit."""

import argparse
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
from pathlib import Path
import re
import secrets
import struct
import threading
import time
from urllib.parse import parse_qs, unquote, urlparse
import webbrowser

from piper_save import write_modified
from save_codec import ROOT, Schema
from app_config import DATA_ROOT, ASSET_ROOT, SAVE_DIR, BACKUP_ROOT, MODIFIED_ROOT, SCHEMA_ROOT, DEMO
import presets
import game_runtime

WEB = ROOT / 'web'
SCHEMA = Schema()
TOKEN = secrets.token_urlsafe(32)
WRITE_LOCK = threading.Lock()
GROUPS = [
    ('common', '常用数值', '', 'star'), ('inventory', '背包物品', 'BagSaveData', 'bag'),
    ('alchemy', '炼金与天赋', 'AlchemySaveData', 'flask'), ('favor', 'NPC 与好感', 'AllFavorData', 'heart'),
    ('staff', '员工与工作站', 'AllStaffSaveData', 'users'), ('tools', '工具与钓鱼', 'AllOprToolSaveData', 'tool'),
    ('farm', '作物与建筑', 'AllMapSaveData', 'sprout'), ('genes', '种子与基因', 'AllHybridData', 'dna'),
    ('all', '全部字段', '', 'code'),
]
LABELS = {'Count':'数量','TalentPoint':'天赋点','Level':'等级','Exp':'经验','favorValue':'好感值',
          'CurrentSan':'当前 SAN','MaxSan':'最大 SAN','SanCostPerTick':'SAN 消耗','CurrentDurability':'当前耐久',
          'GrowthTime':'生长时间','receiveGiftsToday':'今日收礼次数','ConfigId':'物品 ID','Name':'名称',
          'Value':'原始值','IsUnlocked':'已解锁','GameTimeStamp':'游戏时间','LastTimeHour':'上次记录小时',
          'CurrentWorkID':'当前工作','npcID':'角色 ID','SeedLogicID':'种子记录 ID','Timestamp':'时间记录',
          'ItemLogicID':'物品记录 ID','OriginalSeedItemID':'原始种子 ID','State':'当前状态',
          'CurrentLoopRound':'当前轮数','CompletedLoopCount':'已完成轮数','SelectedIndex':'当前选择',
          'LogicID':'记录 ID','UnitConfigID':'角色配置','StaffConfigID':'员工配置','AttributeId':'属性 ID',
          'LastGetExp':'上次获得经验','LastLevel':'上次等级','RedPityNoRedCount':'未出红保底次数',
          'ID':'编号','UnitLogicID':'单位记录 ID','CurrentSettingID':'工作设置','CurrentWorkBuildingID':'工作建筑',
          'BothMapDuty':'跨地图工作','CustomWork':'自定义工作','MainWorkMapID':'工作地图'}


@lru_cache(maxsize=20)
def read_json(relative):
    path = DATA_ROOT / relative.removeprefix('unpacked/')
    if relative.startswith('unpacked/schema/') and not path.exists():
        path = SCHEMA_ROOT / Path(relative).name
    return json.loads(path.read_text(encoding='utf-8'))


ITEMS = read_json('unpacked/configs/物品目录.json')
ITEM_BY_ID = {item['id']: item for item in ITEMS}
ITEM_NAMES = {item['id']: item['name'] for item in ITEMS}
FRIENDLY = {table: {row['id']: row for row in rows} for table, rows in read_json('unpacked/configs/分类目录.json').items()}
FRIENDLY['ItemConfig'] = ITEM_BY_ID
NPC_NAMES = {x['id']: x['name'] for x in read_json('unpacked/configs/分类目录.json').get('UnitConfig', [])}
ITEM_ENUM = next((x for x in read_json('unpacked/schema/enums.json')['types'] if x['name'] == 'Example.lz'), {})
ITEM_TYPES = {x['value']: x['name'] for x in ITEM_ENUM.get('values', [])}


def item_icon(ident):
    reference = ITEM_BY_ID.get(ident, {}).get('raw', {}).get('bnov', '')
    match = re.search(r'Icon_(\d+)$', reference)
    icon_id = match[1] if match else str(ident)
    return f'/assets/items/{icon_id}.webp' if (ASSET_ROOT / 'items' / f'{icon_id}.webp').exists() else None


def save_path(name):
    if not re.fullmatch(r'(?:AUTO_)?SAVE_PIPER_\d+\.bytes', name):
        raise ValueError('请选择有效的游戏存档。')
    path = SAVE_DIR / name
    if not path.is_file():
        raise ValueError('该存档已不存在，请刷新列表。')
    return path


def save_title(name):
    slot = int(re.search(r'_(\d+)\.bytes$', name)[1]) + 1
    return ('演示存档' if DEMO else '自动存档' if name.startswith('AUTO_') else '手动存档') + f' {slot:02d}'


def value_text(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, float):
        return format(value, '.8g')
    return str(value)


def describe_save(name, include_fields=False, snapshot=None):
    path = save_path(name)
    data = path.read_bytes() if snapshot is None else snapshot
    decoded = SCHEMA.decode(data, 'SaveLoadSystem.GameSaveData')
    gold = next((p['Value'] for p in decoded.get('AllAttributeSaveData', {}).get('AttributeParams', []) if p.get('AttributeId') == 901), 0)
    rows = list(SCHEMA.leaves(data)) if include_fields else []
    values = {r['path']: r['value'] for r in rows}
    fields = []
    for row in rows:
        route = row['path']
        parent, _, short = route.rpartition('.')
        title = LABELS.get(short, short)
        detail = ' / '.join(route.split('.')[:-1])
        scale = 1
        offset = 0
        icon = None
        common = False
        group = next((g[0] for g in GROUPS if g[2] and route.startswith(g[2])), 'all')
        if route.startswith('BagSaveData.ItemDataList['):
            ident = values.get(parent + '.ConfigId')
            detail = ITEM_NAMES.get(ident, f'物品 {ident}')
            icon = item_icon(ident)
            common = short == 'Count'
        elif route.startswith('AllFavorData.allNPCData['):
            ident = values.get(parent + '.npcID')
            detail = NPC_NAMES.get(ident, f'角色 {ident}')
            common = short == 'favorValue'
        elif route.startswith('AllStaffSaveData.StaffList['):
            detail = values.get(parent + '.Name', '员工')
            common = short in ('CurrentSan', 'MaxSan')
        elif route.startswith('AllAttributeSaveData.AttributeParams[') and short == 'Value':
            ident = values.get(parent + '.AttributeId')
            title = '金币' if ident == 901 else '沉淀原始值'
            scale = 1000 if ident == 901 else 1
            detail = '当前持有' if ident == 901 else '属性 902'
            common = True
        elif route.startswith('AlchemySaveData.'):
            detail = '炼金成长'
            common = short in ('TalentPoint', 'Exp', 'Level')
        elif route.startswith('AllOprToolSaveData.OprToolDataList['):
            tool_id = values.get(parent+'.ID')
            detail = presets.TOOL_NAMES.get(tool_id,'工具占位记录')
            if short in ('Level','SelectedIndex') and tool_id in presets.TOOL_NAMES:
                offset=1
                title='工具等级' if short=='Level' else '使用范围档位'
        display = value_text(row['value'])
        if scale != 1:
            display = format(Decimal(row['value']) / scale, 'f').rstrip('0').rstrip('.') if row['value'] % scale else str(row['value'] // scale)
        elif offset:
            display = str(row['value']+offset)
        fields.append({'path': route, 'label': title, 'detail': detail, 'value': display,
                       'raw_value': value_text(row['value']), 'type': row['type'], 'kind': row['kind'],
                       'group': group, 'common': common, 'icon': icon, 'scale': scale,'offset':offset})
    return {'name': name, 'title': save_title(name), 'kind': 'auto' if name.startswith('AUTO_') else 'manual',
            'modified': datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec='seconds'),
            'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'gold': format(Decimal(gold) / 1000, 'f'), 'talent': decoded.get('AlchemySaveData', {}).get('TalentPoint', 0),
            'level': decoded.get('AlchemySaveData', {}).get('Level', 0),
            'inventory': len(decoded.get('BagSaveData', {}).get('ItemDataList', [])),
            'field_count': len(fields), 'fields': fields}


def saved_games():
    result = []
    for path in sorted(SAVE_DIR.glob('*SAVE_PIPER_*.bytes'), key=lambda p: (p.name.startswith('AUTO_'), -p.stat().st_mtime)):
        try:
            result.append(describe_save(path.name))
        except Exception as exc:
            result.append({'name': path.name, 'title': save_title(path.name), 'error': str(exc)})
    return result


def items_response():
    result = []
    for item in ITEMS:
        raw = item['raw']
        category = '种子' if '种子' in item['name'] else '鱼类' if '鱼' in item['name'] or item['id'] // 1000 == 18 else '药剂' if any(t in item['name'] for t in ('药剂', '药水')) else '材料与物品'
        result.append({'id': item['id'], 'name': item['name'], 'description': item['description'],
                       'name_en': item['name_en'], 'category': category, 'type_name': ITEM_TYPES.get(raw.get('bnoj'), ''),
                       'icon': item_icon(item['id']),
                       'raw': raw})
    return result


def edit_save(body, export=False, apply=False):
    name = body.get('save', '')
    path = save_path(name)
    original = path.read_bytes()
    if hashlib.sha256(original).hexdigest() != body.get('sha256'):
        raise ValueError('存档在游戏中发生了变化。请重新载入后再修改，避免覆盖新进度。')
    requested = body.get('edits', [])
    if not isinstance(requested, list) or not 1 <= len(requested) <= 1000:
        raise ValueError('请选择 1 至 1000 项修改。')
    original_fields = {f['path']: f for f in SCHEMA.leaves(original)}
    descriptions = {f['path']: f for f in describe_save(name, True, original)['fields']}
    modified = original
    changes = []
    seen = set()
    for requested_edit in requested:
        route = requested_edit.get('path')
        if route not in original_fields or route in seen:
            raise ValueError('修改清单包含重复或未识别的字段。')
        seen.add(route)
        field = original_fields[route]
        info = descriptions[route]
        text = requested_edit.get('value')
        if field['type'] == 'bool':
            if not (isinstance(text, bool) or isinstance(text, str) and text in ('true', 'false')):
                raise ValueError('布尔值必须为 true 或 false。')
            value = text is True or text == 'true'
        elif field['type'] == 'string':
            if not isinstance(text, str) or len(text) > 8192:
                raise ValueError('文字长度不符合要求。')
            value = text
        elif field['type'] in ('float', 'double'):
            value = float(text)
            if not math.isfinite(value):
                raise ValueError('请输入有限的数字。')
            if field['type'] == 'float':
                value = struct.unpack('<f', struct.pack('<f', value))[0]
        else:
            number = (Decimal(str(text))-info.get('offset',0)) * info['scale']
            if not number.is_finite() or number != number.to_integral_value():
                raise ValueError(f'{info["label"]} 的小数位数不符合要求。')
            value = int(number)
            if info['scale'] == 1000 and not 0 <= value <= 999999999000:
                raise ValueError('金币必须介于 0 和 999999999 之间。')
        modified = SCHEMA.edit(modified, route, value)
        changes.append({'path': route, 'label': info['label'], 'detail': info['detail'],
                        'before': info['value'], 'after': value_text(text), 'raw_before': field['value'], 'raw_after': value})
    parsed = {f['path']: f['value'] for f in SCHEMA.leaves(modified)}
    reverted = modified
    for change in reversed(changes):
        if parsed[change['path']] != change['raw_after']:
            raise ValueError('修改后的数值核对未通过。')
        reverted = SCHEMA.edit(reverted, change['path'], change['raw_before'])
    if reverted != original:
        raise ValueError('未修改字段的字节核对未通过，未写入任何存档。')
    response = {'changes': [{k: v for k, v in change.items() if not k.startswith('raw_')} for change in changes],
                'count': len(changes), 'bytes': len(modified), 'original_preserved': True}
    if export or apply:
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        destination = path if apply else MODIFIED_ROOT / f'{path.stem}-{stamp}.bytes'
        with WRITE_LOCK:
            if apply and (DEMO or not game_runtime.status(fresh=True)['can_apply']):
                raise ValueError('请先退出 ThePiper，再直接应用。游戏运行时可以导出副本。')
            backup = write_modified(path, original, modified, destination)
            report = {'source': name, 'output': destination.name, 'backup': backup.name, 'mode':'apply' if apply else 'export', 'created': datetime.now().isoformat(timespec='seconds'), **response}
            (BACKUP_ROOT / (backup.name + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        response.update(filename=destination.name, download=None if apply else f'/downloads/{destination.name}', backup=backup.name, mode=report['mode'])
    return response


def plan_preset(body):
    name=body.get('save','')
    path=save_path(name)
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=body.get('sha256'):
        raise ValueError('存档已更新，请重新读取后生成方案。')
    result=presets.plan(data,body.get('actions'))
    fields={f['path']:f for f in describe_save(name,True,data)['fields']}
    for change in result['changes']:
        info=fields[change['path']]
        change.update(label=info['label'],detail=info['detail'],before=info['value'],icon=info['icon'])
        if info.get('offset'):change['value']=str(int(change['value'])+info['offset'])
    result['edits']=[{'path':change['path'],'value':change['value']} for change in result['changes']]
    result.update(save=name,sha256=body['sha256'])
    return result


def export_history():
    history=[]
    for report_file in sorted((BACKUP_ROOT).glob('*.bak.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:30]:
        try:
            report=json.loads(report_file.read_text(encoding='utf-8'))
            backup=Path(report.get('backup','')).name
            if not backup or not (BACKUP_ROOT/backup).is_file():continue
            changes=report.get('changes',report.get('edits',[]))
            history.append({'source':Path(report.get('source','')).name,'mode':report.get('mode','export'),
                            'created':report.get('created',datetime.fromtimestamp(report_file.stat().st_mtime).isoformat(timespec='seconds')),
                            'count':report.get('count',len(changes)),'backup':backup,'backup_download':'/backups/'+backup})
        except (ValueError,OSError):continue
    return history


class Handler(BaseHTTPRequestHandler):
    server_version = 'DawnAtelier/1.0'

    def log_message(self, format, *args):
        pass

    def valid_host(self):
        return self.headers.get('Host', '') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def send_bytes(self, content, mime, status=200, extra=None):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store' if mime.startswith('application/json') else 'no-cache')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(content)

    def json(self, value, status=200):
        self.send_bytes(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8'), 'application/json; charset=utf-8', status)

    def do_GET(self):
        if not self.valid_host():
            self.json({'error': '不支持的访问地址。'}, 403)
            return
        parsed = urlparse(self.path)
        route = unquote(parsed.path)
        query = parse_qs(parsed.query)
        try:
            if route == '/api/health':
                self.json({'app': 'dawn-atelier', 'ready': True,'demo':DEMO})
            elif route == '/api/bootstrap':
                self.json({'app': 'dawn-atelier', 'token': TOKEN, 'saves': saved_games(),
                           'version':'2.0','runtime':game_runtime.status(),'demo':DEMO,
                           'stats': read_json('unpacked/configs/index.json'),
                           'resources': read_json('unpacked/resources/summary.json'),
                           'groups': [{'id': g[0], 'label': g[1], 'icon': g[3]} for g in GROUPS]})
            elif route == '/api/presets':
                self.json(presets.catalog())
            elif route == '/api/runtime':
                self.json(game_runtime.status())
            elif route == '/api/items':
                self.json(items_response())
            elif route == '/api/save':
                self.json(describe_save(query.get('name', [''])[0], True))
            elif route == '/api/table':
                name = query.get('name', [''])[0]
                names = {t['table'] for t in read_json('unpacked/configs/index.json')['tables']}
                if name not in names:
                    raise ValueError('配置表不存在。')
                data = read_json('unpacked/configs/' + name + '.json')
                keyword = query.get('q', [''])[0].casefold()[:200]
                page = max(0, int(query.get('page', ['0'])[0]))
                selected = []
                for ident, row in zip(data['ids'], data['rows']):
                    friendly = FRIENDLY.get(name, {}).get(ident, {})
                    title = friendly.get('name', '')
                    description = friendly.get('description', '')
                    if not keyword or keyword in (str(ident) + title + description + json.dumps(row, ensure_ascii=False)).casefold():
                        selected.append({'id': ident, 'name': title, 'description': description, 'data': row})
                self.json({'table': name, 'total': len(selected), 'page': page, 'rows': selected[page*40:(page+1)*40]})
            elif route == '/api/exports':
                folder = MODIFIED_ROOT
                files = [{'name': p.name, 'bytes': p.stat().st_size,
                          'modified': datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='seconds'),
                          'download': '/downloads/' + p.name} for p in sorted(folder.glob('*.bytes'), key=lambda p: p.stat().st_mtime, reverse=True)] if folder.exists() else []
                backups = list((BACKUP_ROOT).glob('*.bak'))
                self.json({'files': files, 'backup_count': len(backups),'history':export_history()})
            elif route.startswith('/backups/'):
                name=route.rsplit('/',1)[-1]
                if not re.fullmatch(r'(?:AUTO_)?SAVE_PIPER_\d+\.bytes\.\d{8}-\d{6}-\d{6}\.bak',name):
                    raise ValueError('备份文件名无效。')
                path=BACKUP_ROOT/name
                restored_name=name.split('.bytes.')[0]+'.bytes'
                self.send_bytes(path.read_bytes(),'application/octet-stream',extra={'Content-Disposition':f'attachment; filename="{restored_name}"'})
            elif route.startswith('/downloads/'):
                name = route.rsplit('/', 1)[-1]
                if not re.fullmatch(r'(?:AUTO_)?SAVE_PIPER_\d+-[\d-]+\.bytes', name):
                    raise ValueError('下载文件名无效。')
                path = MODIFIED_ROOT / name
                self.send_bytes(path.read_bytes(), 'application/octet-stream', extra={'Content-Disposition': f'attachment; filename="{name}"'})
            else:
                relative = 'index.html' if route == '/' else route.lstrip('/')
                if relative not in ('index.html', 'app.js', 'style.css','presets-ui.js','presets.css') and not relative.startswith(('assets/','brand/')):
                    self.json({'error': '页面不存在。'}, 404)
                    return
                base = ASSET_ROOT if relative.startswith('assets/') else WEB
                path = (base / relative.removeprefix('assets/')).resolve()
                if not path.exists() and relative in ('assets/gameicon.webp','assets/piper.webp'):
                    path=WEB/'brand'/('emblem.svg' if 'gameicon' in relative else 'botanical.svg')
                    base=WEB
                if not path.is_relative_to(base.resolve()) or not path.is_file():
                    self.json({'error': '页面不存在。'}, 404)
                    return
                mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
                if path.suffix in ('.js', '.css', '.html', '.svg'):
                    mime += '; charset=utf-8'
                self.send_bytes(path.read_bytes(), mime)
        except Exception as exc:
            self.json({'error': str(exc)}, 400)

    def do_POST(self):
        allowed_origin = (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}')
        if not self.valid_host() or self.headers.get('Origin') not in allowed_origin or self.headers.get('X-Dawn-Token') != TOKEN:
            self.json({'error': '请在本地工作台中执行此操作。'}, 403)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length < 2_000_000:
                raise ValueError('修改清单过大或为空。')
            body = json.loads(self.rfile.read(length))
            if self.path=='/api/preset-plan':
                self.json(plan_preset(body))
                return
            if self.path not in ('/api/preview', '/api/export','/api/apply'):
                self.json({'error': '操作不存在。'}, 404)
                return
            self.json(edit_save(body, self.path == '/api/export',self.path == '/api/apply'))
        except Exception as exc:
            self.json({'error': str(exc)}, 400)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--demo', action='store_true', help='Use synthetic example saves')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    if args.open:
        webbrowser.open(f'http://127.0.0.1:{args.port}')
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
