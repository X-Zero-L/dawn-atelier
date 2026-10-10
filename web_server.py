"""Local, dependency-free web UI for the extracted ThePiper toolkit."""

import argparse
from datetime import datetime
from functools import lru_cache
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import struct
import threading
from urllib.parse import parse_qs, unquote, urlparse
import webbrowser

from atelier import Editor, Snapshot
from piper_adapter import ThePiperAdapter
from save_codec import ROOT
from app_paths import app_version
from app_config import DATA_ROOT, ASSET_ROOT, SAVE_DIR, BACKUP_ROOT, MODIFIED_ROOT, DEMO, GAME_DIR
from compatibility import require_prepared, require_unchanged_install

COMPATIBILITY = None if DEMO else require_prepared(GAME_DIR, DATA_ROOT)


def check_installation():
    if not DEMO:
        require_unchanged_install(GAME_DIR, DATA_ROOT, COMPATIBILITY)
import presets
import inventory
import game_runtime
import progression

WEB = ROOT / 'web'
TOKEN = secrets.token_urlsafe(32)
WRITE_LOCK = threading.Lock()
from piper_editor import (GROUPS, SCHEMA as SCHEMA, ITEMS, FRIENDLY, ITEM_TYPES,
                          read_json, item_icon, save_path, save_title, describe_save, transform_save)
ADAPTER = ThePiperAdapter()
EDITOR = Editor(ADAPTER, BACKUP_ROOT)


def saved_games():
    result = []
    for path in sorted(SAVE_DIR.glob('*SAVE_PIPER_*.bytes'), key=lambda p: (p.name.startswith('AUTO_'), -p.stat().st_mtime)):
        try:
            result.append(describe_save(path.name))
        except Exception as exc:
            result.append({'name': path.name, 'title': save_title(path.name), 'error': str(exc)})
    return result


@lru_cache(maxsize=64)
def indexed_save_summary(name, data):
    return describe_save(name, snapshot=data)


def save_index():
    """Read current filenames and identities without decoding every save."""
    result = []
    for path in SAVE_DIR.glob('*SAVE_PIPER_*.bytes'):
        if not re.fullmatch(r'(?:AUTO_)?SAVE_PIPER_\d+\.bytes', path.name):
            continue
        try:
            before = path.stat()
            data = path.read_bytes()
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                continue
            summary = {}
            try:
                summary = indexed_save_summary(path.name, data)
            except (ValueError, KeyError, IndexError, struct.error) as error:
                summary = {'error':'这份存档暂时无法读取，游戏可能正在保存。稍候刷新重试。'}
            result.append({**summary, 'name':path.name,'title':save_title(path.name),
                           'kind':'auto' if path.name.startswith('AUTO_') else 'manual',
                           'modified':datetime.fromtimestamp(after.st_mtime).isoformat(timespec='seconds'),
                           'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                           '_mtime':after.st_mtime_ns})
        except OSError:
            continue
    result.sort(key=lambda row:(row['name'].startswith('AUTO_'),-row['_mtime']))
    return [{key:value for key,value in row.items() if key!='_mtime'} for row in result]


def items_response():
    result = []
    for item in ITEMS:
        raw = item['raw']
        category = '种子' if '种子' in item['name'] else '鱼类' if '鱼' in item['name'] or item['id'] // 1000 == 18 else '药剂' if any(t in item['name'] for t in ('药剂', '药水')) else '材料与物品'
        result.append({'id': item['id'], 'name': item['name'], 'description': item['description'],
                       'name_en': item['name_en'], 'category': category, 'type_name': ITEM_TYPES.get(raw.get('bnoj'), ''),
                       'icon': item_icon(item['id']),
                       'can_add':inventory.addition_supported(raw),
                       'raw': raw})
    return result


def edit_save(body, export=False, apply=False):
    check_installation()
    name = body.get('save', '')
    path = save_path(name)
    snapshot = Snapshot.capture(path)
    if snapshot.sha256 != body.get('sha256'):
        raise ValueError('存档在游戏中发生了变化。请重新载入后再修改，避免覆盖新进度。')
    operations = body.get('edits', [])
    plan = EDITOR.preview(snapshot, operations)
    _, response = transform_save(snapshot.data, operations)
    response.update(plan_id=plan.plan_id, adapter_id=ADAPTER.descriptor.id)
    if export or apply:
        if body.get('plan_id') != plan.plan_id:
            raise ValueError('修改方案已变化或尚未预览，请重新查看修改清单后再保存。')
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        destination = path if apply else MODIFIED_ROOT / f'{path.stem}-{stamp}.bytes'
        with WRITE_LOCK:
            check_installation()
            report = EDITOR.commit(plan, destination, approval=body['plan_id'], mode='apply' if apply else 'export')
        response.update(filename=destination.name, download=None if apply else f'/downloads/{destination.name}',
                        backup=Path(report['backup']).name, mode=report['mode'])
        if report.get('audit_error'):
            response['warning'] = '存档已保存并备份，但操作记录写入失败：' + report['audit_error']
        if report.get('warnings'):
            response['warning'] = response.get('warning', '') + ' 存档已保存，临时文件暂未清理。'
    return response


def plan_preset(body):
    check_installation()
    name=body.get('save','')
    path=save_path(name)
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=body.get('sha256'):
        raise ValueError('存档已更新，请重新读取后生成方案。')
    result=presets.plan(data,body.get('actions'))
    return enrich_plan(result, body, data)


def plan_progression(body):
    check_installation()
    name=body.get('save','')
    data=save_path(name).read_bytes()
    if hashlib.sha256(data).hexdigest()!=body.get('sha256'):
        raise ValueError('存档已更新，请重新读取后生成方案。')
    result=progression.plan(data,body.get('kind'),body.get('target'),body.get('talent_ids'))
    return enrich_plan(result,body,data)


def enrich_plan(result, body, data):
    name=body['save']
    fields={f['path']:f for f in describe_save(name,True,data)['fields']}
    for change in result['changes']:
        change.pop('raw_value',None)
        if change.get('operation')=='add_item':
            info=inventory.virtual_field(change['item_id'])
            info['icon']=item_icon(change['item_id'])
            change['field']=info
            change['icon']=info['icon']
            continue
        info=fields[change['path']]
        change.update(label=info['label'],detail=info['detail'],before=info['value'],icon=info['icon'])
        if info.get('offset'):change['value']=str(int(change['value'])+info['offset'])
    result['edits']=[{'path':change['path'],'value':change['value'],**({'field':change['field']} if change.get('operation')=='add_item' else {})} for change in result['changes']]
    result.update(save=name,sha256=body['sha256'])
    return result


def export_history():
    history=[]
    reports = list(BACKUP_ROOT.glob('*.bak.json')) + list(EDITOR.backup_root.glob('*.bak.json'))
    for report_file in sorted(reports,key=lambda p:p.stat().st_mtime,reverse=True)[:30]:
        try:
            report=json.loads(report_file.read_text(encoding='utf-8'))
            backup=Path(report.get('backup','')).name
            if not backup or not (report_file.parent/backup).is_file():continue
            changes=report.get('changes',report.get('edits',report.get('operations',[])))
            history.append({'source':Path(report.get('source','')).name,'mode':report.get('mode','export'),
                            'created':report.get('created',datetime.fromtimestamp(report_file.stat().st_mtime).isoformat(timespec='seconds')),
                            'count':report.get('count',len(changes)),'backup':backup,'backup_download':'/backups/'+backup})
        except (ValueError,OSError):continue
    return history


class Handler(BaseHTTPRequestHandler):
    server_version = 'DawnAtelier/' + app_version()

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
        ancestor = getattr(self.server, 'desktop_origin', None) or "'none'"
        self.send_header('Content-Security-Policy', f"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors {ancestor}; base-uri 'none'")
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
                self.json({'app': 'dawn-atelier', 'ready': True,'demo':DEMO,'compatibility':COMPATIBILITY})
            elif route == '/api/bootstrap':
                self.json({'app': 'dawn-atelier', 'token': TOKEN, 'saves': saved_games(),
                           'desktop_origin': getattr(self.server, 'desktop_origin', None),
                           'version':app_version(),'adapter':ADAPTER.descriptor.to_dict(),'runtime':game_runtime.status(),'demo':DEMO,
                           'stats': read_json('unpacked/configs/index.json'),
                           'resources': read_json('unpacked/resources/summary.json'),
                           'groups': [{'id': g[0], 'label': g[1], 'icon': g[3]} for g in GROUPS]})
            elif route == '/api/adapters':
                from workbench import registry
                from compatibility import profiles
                self.json({'active': ADAPTER.descriptor.id, 'adapters': registry().descriptors(),
                           'compatibility':COMPATIBILITY, 'demo':DEMO,
                           'reviewed_builds':[profile['id'] for profile in profiles()]})
            elif route == '/api/presets':
                self.json(presets.catalog())
            elif route == '/api/saves':
                check_installation()
                self.json({'saves':save_index()})
            elif route == '/api/runtime':
                self.json(game_runtime.status())
            elif route == '/api/items':
                self.json(items_response())
            elif route == '/api/save':
                check_installation()
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
                backups = list(BACKUP_ROOT.glob('*.bak')) + list(EDITOR.backup_root.glob('*.bak'))
                self.json({'files': files, 'backup_count': len(backups),'history':export_history()})
            elif route.startswith('/backups/'):
                name=route.rsplit('/',1)[-1]
                if not re.fullmatch(r'(?:AUTO_)?SAVE_PIPER_\d+\.bytes\.\d{8}-\d{6}-\d{6}\.bak',name):
                    raise ValueError('备份文件名无效。')
                path=EDITOR.backup_root/name
                if not path.is_file():
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
                if relative not in ('index.html', 'app.js', 'style.css','presets-ui.js','presets.css','progression-ui.js','progression.css','save-refresh.js','adapters-ui.js','adapters.css',
                                    'desktop/index.html','desktop/launcher.js','desktop/launcher.css') and not relative.startswith(('assets/','brand/')):
                    self.json({'error': '页面不存在。'}, 404)
                    return
                base = ASSET_ROOT if relative.startswith('assets/') else ROOT if relative.startswith('desktop/') else WEB
                path = (base / relative.removeprefix('assets/')).resolve()
                if not path.exists() and relative in ('assets/gameicon.webp','assets/piper.webp'):
                    path=WEB/'brand'/('emblem.svg' if 'gameicon' in relative else 'botanical.svg')
                    base=WEB
                elif not path.exists() and re.fullmatch(r'assets/items/\d+\.webp',relative):
                    path=WEB/'brand/botanical.svg'
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
        if self.path == '/api/desktop-stop' and getattr(self.server, 'desktop_token', None):
            if not self.valid_host() or not secrets.compare_digest(self.headers.get('X-Dawn-Control', ''), self.server.desktop_token):
                self.json({'error': '无效的桌面会话。'}, 403)
                return
            self.server.stopping = True
            self.json({'ok': True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if getattr(self.server, 'stopping', False):
            self.json({'error': '工坊正在关闭，请稍候。'}, 503)
            return
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
            if self.path=='/api/progression-plan':
                self.json(plan_progression(body))
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
    parser.add_argument('--ready-file', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--fallback-port', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError:
        if not args.fallback_port:
            raise
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = False
    server.desktop_token = secrets.token_urlsafe(32) if args.ready_file else None
    origin = os.environ.get('DAWN_DESKTOP_ORIGIN', '')
    server.desktop_origin = origin if args.ready_file and re.fullmatch(r'http://127\.0\.0\.1:\d{1,5}', origin) else None
    if args.ready_file:
        args.ready_file.parent.mkdir(parents=True, exist_ok=True)
        args.ready_file.write_text(json.dumps({'port': server.server_port, 'pid': os.getpid(),
                                              'token': server.desktop_token,
                                              'session': os.environ.get('DAWN_DESKTOP_SESSION')}), encoding='utf-8')
    if args.open:
        webbrowser.open(f'http://127.0.0.1:{server.server_port}')
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
