"""Match reviewed save/config resources without pinning Steam build dates."""

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from app_paths import APP_ROOT
from unpack_unity import Reader, bundle_files, serialized_objects

PROFILE = APP_ROOT/'schemas/blazblue/resource-contract.json'


def resource_bytes(root, row):
    if not re.fullmatch(r'm_\d+\.m',row.get('m','')) or type(row.get('s')) is not int or row['s']<0:
        raise ValueError('游戏资源索引无效。')
    path=(root/row['m']).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('游戏资源路径无效。')
    with path.open('rb') as stream:
        stream.seek(row['s'])
        header=Reader(stream.read(256))
        if header.string()!='UnityFS':
            raise ValueError('游戏配置资源格式变化，请更新适配器。')
        header.one('I');header.string();header.string()
        length=header.one('Q')
        if not 0<length<=32*1024*1024:
            raise ValueError('游戏配置资源长度无效。')
        stream.seek(row['s']);data=stream.read(length)
    if len(data)!=length:
        raise ValueError('游戏资源正在更新或不完整。')
    return data


@lru_cache(maxsize=32)
def textasset_hash(data):
    _,files=bundle_files(data)
    payloads=[]
    for entry,content in files:
        if entry['name'].endswith(('.resS','.resource')):
            continue
        _,objects,endian=serialized_objects(content)
        for obj in objects:
            if obj['class_id']==49:
                reader=Reader(content[obj['offset']:obj['offset']+obj['size']],endian)
                reader.sized_string()
                payload=reader.take(reader.one('i'))
                payloads.append(hashlib.sha256(payload).hexdigest())
    if len(payloads)!=1:
        raise ValueError('游戏配置资源包含未确认的对象。')
    return payloads[0]


def inspect_installation(game_dir):
    if game_dir is None:
        raise ValueError('未找到游戏安装。请安装 Steam 版《苍翼：混沌效应》，或设置 BLAZBLUE_GAME_DIR。')
    root=Path(game_dir)/'BlazblueEntropyEffect_Data/StreamingAssets/ab'
    profile=json.loads(PROFILE.read_text(encoding='utf-8'))
    index=json.loads((root/'merge.json').read_text(encoding='utf-8-sig'))
    expected=profile['resources']
    selected={}
    for row in index:
        if row.get('r') in expected:
            if row['r'] in selected:
                raise ValueError('游戏资源索引重复，无法核对兼容性。')
            selected[row['r']]=row
    if set(selected)!=set(expected):
        raise ValueError('当前游戏缺少已确认的存档资源，请更新适配器。')
    observed={}
    for name,wanted in expected.items():
        actual=textasset_hash(resource_bytes(root,selected[name]))
        if actual!=wanted:
            raise ValueError('游戏存档或资源规则已变化，请等待新版适配：'+name)
        observed[name]=actual
    # Resource identities, not date/build IDs, are the editing contract.
    return {'contract':profile['id'],'resources':observed}
