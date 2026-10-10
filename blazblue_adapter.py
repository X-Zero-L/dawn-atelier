"""Confirmed local resource counts for BlazBlue Entropy Effect."""

import os
from pathlib import Path
import re

from atelier import Adapter, Capability, GameDescriptor
from blazblue_codec import decode_save, read_modules, read_pack, replace_module, set_pack_count

PACKS = {'currency':'ModelPlayerNewCurrencyPack', 'item':'ModelPlayerNewItemPack'}
RESOURCES = {
    'currency:1':('AP','日常资源','在游戏中消费 AP；数量调整不会补记历史消费任务。'),
    'item:4001':('原型体解析器','日常资源','准备角色解析所需资源，回游戏选择并解析原型体。'),
    'item:9001':('颜色印记','日常资源','回游戏使用颜色印记兑换可用配色。'),
    'item:4091':('艾希解析器','联动资源','仅调整已有记录；联动关卡、剧情和领取状态保持原样。'),
    'item:4092':('枭首者解析器','联动资源','仅调整已有记录；联动关卡、剧情和领取状态保持原样。'),
    **{f'item:{6000+n}':(f'挑战券（第{n}轮）','挑战资源','仅调整已有记录；轮次、挑战完成状态和领奖仍由游戏处理。') for n in range(1,5)},
}
MAX_COUNT = 99_999_999


def find_game():
    explicit=os.environ.get('BLAZBLUE_GAME_DIR')
    if explicit:
        return Path(explicit).expanduser().resolve()
    roots=[]
    if os.name=='nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam') as handle:
                roots.append(Path(winreg.QueryValueEx(handle,'SteamPath')[0]))
        except OSError:
            pass
        for name in ('PROGRAMFILES(X86)','PROGRAMFILES'):
            if os.environ.get(name):
                roots.append(Path(os.environ[name])/'Steam')
    libraries=list(roots)
    for root in roots:
        index=root/'steamapps/libraryfolders.vdf'
        if index.is_file():
            libraries += [Path(value.replace('\\\\','\\')) for value in re.findall(r'"path"\s+"([^"]+)"',index.read_text(encoding='utf-8',errors='replace'))]
    return next((library/'steamapps/common/BlazblueEntropyEffect' for library in libraries
                 if (library/'steamapps/common/BlazblueEntropyEffect/BlazblueEntropyEffect.exe').is_file()),None)


def discover_saves():
    explicit=os.environ.get('BLAZBLUE_SAVE_DIR')
    if explicit:
        roots=[Path(explicit).expanduser().resolve()]
    else:
        base=Path.home()/'AppData/LocalLow/91Act/BlazBlueEntropyEffect'
        roots=[*base.glob('Steam/*/Save'),base/'Save']
    result=[]
    for root in roots:
        if root.is_dir():
            result += [path for path in root.iterdir() if re.fullmatch(r'[1-9]\d{0,2}',path.name) and path.is_file() and not path.is_symlink()]
    return sorted(set(result))


def runtime_status():
    # Reuse the process enumeration primitive with an explicit executable name.
    from process_guard import process_status
    return process_status('BlazblueEntropyEffect.exe')


class BlazBlueAdapter(Adapter):
    descriptor=GameDescriptor('blazblue','苍翼：混沌效应','2',(
        Capability('resources','AP 与解析器','调整已有资源数量，准备下一次训练。'),
        Capability('crossover','联动与挑战资源','核对已有解析器与挑战券，保留剧情和到期时间。'),
        Capability('presets','一键资源准备','补到目标数量，预览后导出或备份应用。'),
        Capability('actors','角色解析准备','查看 17 位角色记录，按未解锁清单计算解析器。'),
    ))
    notes=[
        '只列出存档中已存在、含义已确认的资源。缺少的物品不会凭空新增。',
        '修改 AP、解析器或挑战券的数量，不会自动完成剧情、角色解析、轮次、任务和领取记录。请回游戏使用资源。',
        '保留物品到期时间和未修改的全部模型数据。原始存档备份保存在工坊数据目录。',
        '角色属性、潜能、策略和直接解锁尚未开放写入；当前完成了格式与静态逻辑核对，未完成游戏内读档验证。',
    ]
    presets=[
        {'id':'starter','title':'轻松训练','description':'10 万 AP，99 个已有原型体解析器。','targets':{'currency:1':100000,'item:4001':99}},
        {'id':'supplies','title':'充实储备','description':'100 万 AP，999 个解析器与已有颜色印记。','targets':{'currency:1':1000000,'item:4001':999,'item:9001':999}},
        {'id':'crossover','title':'联动与挑战准备','description':'已有联动解析器与挑战券补至 99；保留关卡和剧情。','targets':{key:99 for key in RESOURCES if key not in ('currency:1','item:4001','item:9001')}},
    ]

    def __init__(self, game_dir=None):
        self.game_dir=Path(game_dir) if game_dir else find_game()
        self._installation=None

    def _parse(self, data):
        document=decode_save(data)
        models=read_modules(document.payload)
        if 'ModelPlayer' not in models or any(name not in models for name in PACKS.values()):
            raise ValueError('此存档使用旧结构或缺少玩家资源模型，请先用当前游戏读取并重新保存。')
        fields=[]
        for kind,model in PACKS.items():
            for row in read_pack(models[model]):
                key=f'{kind}:{row["id"]}'
                if key not in RESOURCES:
                    continue
                if not 0<=row['count']<=2147483647:
                    raise ValueError('资源数量超出已确认的 int32 范围，未开放修改。')
                label,group,description=RESOURCES[key]
                fields.append({'id':key,'label':label,'value':row['count'],'min':0,'max':MAX_COUNT,
                               'group':group,'description':description})
        return document,models,fields

    def inspect(self, data):
        from blazblue_actors import overview
        document,models,fields=self._parse(data)
        return {**overview(models,fields),'fields':fields,'summary':{'游戏':'苍翼：混沌效应','存档模型':len(models),
                '已确认可修改项':len(fields),'压缩文件字节数':len(data),'解压后字节数':len(document.payload),
                '存档格式':'LZ4 / protobuf · 玩家独立资源包'},'notes':self.notes}

    def _edit(self, data, operations):
        document,models,fields=self._parse(data)
        available={row['id']:row for row in fields}
        changed=document.payload
        inverse=[]
        seen=set()
        for operation in operations:
            if not isinstance(operation,dict) or set(operation)!={'action','target','value'} or operation['action']!='set':
                raise ValueError('请使用已确认的资源数量操作。')
            target=operation['target']
            if not isinstance(target,str) or target in seen or target not in available:
                raise ValueError('修改包含重复、不存在或尚未开放的资源。')
            value=operation['value']
            if type(value) is not int or not 0<=value<=MAX_COUNT:
                raise ValueError(f'数量必须为 0 至 {MAX_COUNT:,} 的整数。')
            seen.add(target)
            kind,ident=target.split(':')
            model=PACKS[kind]
            current=read_modules(changed)[model]
            changed=replace_module(changed,model,set_pack_count(current,int(ident),value))
            inverse.append((model,int(ident),available[target]['value']))
        restored=changed
        for model,ident,count in reversed(inverse):
            restored=replace_module(restored,model,set_pack_count(read_modules(restored)[model],ident,count))
        if restored!=document.payload:
            raise ValueError('未修改内容的字节保留检查失败。')
        modified=document.encode(changed)
        if decode_save(modified).payload!=changed:
            raise ValueError('修改后的存档回读检查失败。')
        return modified

    def transform(self, data, operations):
        return self._edit(data,operations)

    def validate(self, original, modified, operations):
        if modified!=self._edit(original,operations):
            raise ValueError('修改结果与方案不一致。')

    def compatibility(self, snapshot):
        self._parse(snapshot.data)
        from blazblue_install import inspect_installation
        evidence=inspect_installation(self.game_dir)
        if self._installation is None:
            self._installation=evidence
        if evidence!=self._installation:
            raise ValueError('游戏资料在工作台运行期间发生变化，请重新打开工作台。')
        return {'format':'blazblue-split-packs-v1','installation':evidence}

    def runtime(self, snapshot, mode):
        if mode=='apply' and not runtime_status()['can_apply']:
            raise ValueError('请退出《苍翼：混沌效应》后再直接应用；游戏运行时可以导出副本。')
