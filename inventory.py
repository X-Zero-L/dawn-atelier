"""Catalogue-aware inventory supply and reversible additions to an existing bag."""

import json
import re

from app_config import DATA_ROOT
from save_codec import Schema, encode_varint, replace_payload, wire_fields

SCHEMA = Schema()
ITEMS = json.loads((DATA_ROOT/'configs/物品目录.json').read_text(encoding='utf-8'))
ITEM_BY_ID = {item['id']: item for item in ITEMS}
PLAIN_ITEM_TYPES = {4, 5, 6, 7, 8, 9, 10, 16}
SEED_TYPES = {1, 2, 3, 15}
LINKED_SEED_TYPES = {1, 2, 15}
INT_MAX = 2147483647
ADD_PATH = re.compile(r'InventoryAdd\[(\d+)\]')


def stackable(config):
    return config.get('bnol') == 1 and config.get('bnok', 0) > 1


def addition_supported(config):
    kind=config.get('bnoj')
    return (stackable(config) and kind in PLAIN_ITEM_TYPES|LINKED_SEED_TYPES
            and config.get('bnot',0)!=8
            and (kind!=10 or config.get('bnot',0)==0))


def seed_link(decoded,item_id,kind):
    """Reuse a detached seed of this configuration; refuse ambiguous links."""
    section=decoded.get('AllSeedSaveData',{})
    member='StaffSeedSaveDataList' if kind==15 else 'SeedSaveDataList'
    candidates=[]
    for index,entry in enumerate(section.get(member,[])):
        seed=entry.get('Data',{}) if kind==15 else entry
        if seed.get('SeedConfigID')==item_id:
            route=f'AllSeedSaveData.{member}[{index}]'+('.Data' if kind==15 else '')
            candidates.append((seed,route))
    if len(candidates)>1:
        return None,'同一配置有多份种子记录，保留现有关系'
    if candidates:
        seed,route=candidates[0]
        if not 0<seed.get('SeedLogicID',0)<INT_MAX:
            return None,'已有种子记录的编号无效'
        if seed.get('ItemLogicID',-1)>0:
            return None,'已有种子记录仍关联其他物品'
        if 'ItemLogicID' not in seed:
            return None,'已有种子记录缺少反向引用字段'
        return {'seed_id':seed['SeedLogicID'],'item_path':route+'.ItemLogicID'},None
    return None,None


def virtual_path(item_id):
    return f'InventoryAdd[{item_id}]'


def parse_virtual_path(route):
    match=ADD_PATH.fullmatch(route or '')
    return int(match[1]) if match else None


def virtual_field(item_id):
    item=ITEM_BY_ID.get(item_id)
    if item is None or not addition_supported(item['raw']):
        raise ValueError('这个物品需要专用记录，不能直接新增到背包。')
    return {'path':virtual_path(item_id),'label':'新增物品','detail':item['name'],
            'value':'0','raw_value':'0','type':'int32','kind':'primitive','group':'inventory',
            'common':False,'scale':1,'offset':0,'readonly':False,'operation':'add_item',
            'item_id':item_id,'min':1,'max':item['raw']['bnok']}


def missing_items(data, target, only_ids=None):
    decoded=SCHEMA.decode(data,'SaveLoadSystem.GameSaveData')
    bag=decoded.get('BagSaveData',{})
    if not isinstance(bag.get('ItemDataList',[]),list):
        raise ValueError('当前存档的背包格式无法识别。')
    owned={row.get('ConfigId') for row in bag.get('ItemDataList',[])}
    changes=[]
    exclusions=[]
    for item in ITEMS:
        ident=item['id'];config=item['raw']
        if only_ids is not None and ident not in only_ids:continue
        if ident in owned:continue
        if addition_supported(config):
            if config.get('bnoj') in LINKED_SEED_TYPES:
                _,reason=seed_link(decoded,ident,config['bnoj'])
                if reason:
                    exclusions.append({'id':ident,'name':item['name'],'reason':reason})
                    continue
            quantity=min(target,config['bnok'])
            changes.append({'path':virtual_path(ident),'value':str(quantity),'before':'0',
                            'label':'新增物品','detail':item['name'],'item_id':ident,
                            'operation':'add_item','action':'super_inventory','scale':1})
        elif stackable(config) and config.get('bnoj')==3:
            exclusions.append({'id':ident,'name':item['name'],'reason':'杂交种子需要原始种子、成长时间与基因数据'})
    return changes,exclusions


def _encode_record(type_name,record):
    definitions={field['name']:field for field in SCHEMA.confirmed(type_name).values()}
    result=bytearray()
    for name,value in record.items():
        field=definitions[name]
        if field['wire_type']==0:
            result.extend(encode_varint(field['protobuf_tag']<<3))
            result.extend(encode_varint(value&0xFFFFFFFFFFFFFFFF))
        elif field['wire_type']==2 and field['type']['kind']=='message':
            result.extend(_entry(field['protobuf_tag'],_encode_record(field['type']['name'],value)))
        else:
            raise ValueError('物品存档结构与支持版本不一致。')
    return bytes(result)


def _entry(tag,payload):
    return encode_varint((tag<<3)|2)+encode_varint(len(payload))+payload


def _root_field(data,tag):
    found=[field for field in wire_fields(data) if field['tag']==tag and field['wire']==2]
    if len(found)>1:
        raise ValueError('存档包含重复的数据区域，无法新增物品。')
    return found[0] if found else None


def _replace_root(data,tag,payload):
    field=_root_field(data,tag)
    return replace_payload(data,field,payload) if field else data+_entry(tag,payload)


def append_items(data, additions):
    """Append ordinary items and matched seed records, retaining exact inverse patches."""
    if not additions:return data,None,[]
    root_fields=wire_fields(data)
    bag_tag=next(f['protobuf_tag'] for f in SCHEMA.confirmed('SaveLoadSystem.GameSaveData').values() if f['name']=='BagSaveData')
    bag_fields=[field for field in root_fields if field['tag']==bag_tag and field['wire']==2]
    if len(bag_fields)!=1:
        raise ValueError('当前存档没有唯一的背包记录，无法新增物品。')
    original_bag=bag_fields[0]
    original_data=data
    decoded=SCHEMA.decode(data,'SaveLoadSystem.GameSaveData')
    bag=SCHEMA.decode(original_bag['value'],'SaveLoadSystem.BagData')
    owned={row.get('ConfigId') for row in bag.get('ItemDataList',[])}
    leaves=list(SCHEMA.leaves(data))
    next_id=max([0]+[f['value'] for f in leaves if f['path'].endswith('.ItemLogicID') and isinstance(f['value'],int)])+1
    next_seed=max([0]+[f['value'] for f in leaves if f['path'].endswith('.SeedLogicID') and isinstance(f['value'],int)])+1
    root_schema=SCHEMA.confirmed('SaveLoadSystem.GameSaveData')
    seed_tag=next(f['protobuf_tag'] for f in root_schema.values() if f['name']=='AllSeedSaveData')
    original_seed=_root_field(data,seed_tag)
    seed_lists={f['name']:f['protobuf_tag'] for f in SCHEMA.confirmed('SaveLoadSystem.AllSeedSaveData').values()}
    new_seed_payload=bytearray()
    seed_changed=False
    item_tag=next(f['protobuf_tag'] for f in SCHEMA.confirmed('SaveLoadSystem.BagData').values() if f['name']=='ItemDataList')
    payload=bytearray(original_bag['value'])
    records=[]
    seen=set()
    for addition in additions:
        ident=parse_virtual_path(addition.get('path'))
        field=virtual_field(ident)
        if ident in seen or ident in owned:
            raise ValueError('新增列表中有重复或已经拥有的物品，请重新生成方案。')
        seen.add(ident)
        value=addition.get('value')
        if isinstance(value,bool) or not re.fullmatch(r'\d+',str(value)):
            raise ValueError('新增物品数量必须是正整数。')
        count=int(value)
        if not 1<=count<=field['max']:
            raise ValueError(f"{field['detail']}的数量必须介于 1 和 {field['max']} 之间。")
        if next_id>=INT_MAX:
            raise ValueError('物品记录编号已达到上限，无法新增。')
        record={'ConfigId':ident,'Count':count,'Timestamp':0,'SeedLogicID':0,'OriginalSeedItemID':-1,'ItemLogicID':next_id}
        kind=ITEM_BY_ID[ident]['raw'].get('bnoj')
        if kind in LINKED_SEED_TYPES:
            link,reason=seed_link(decoded,ident,kind)
            if reason:
                raise ValueError(f"{field['detail']}：{reason}。")
            if link:
                record['SeedLogicID']=link['seed_id']
                data=SCHEMA.edit(data,link['item_path'],next_id)
            else:
                if next_seed>=INT_MAX:
                    raise ValueError('种子记录编号已达到上限，无法新增。')
                record['SeedLogicID']=next_seed
                seed={'SeedLogicID':next_seed,'SeedConfigID':ident,'ItemLogicID':next_id}
                next_seed+=1
                if kind==15:
                    encoded=_encode_record('SaveLoadSystem.StaffSeedSaveData',{'Data':seed})
                    new_seed_payload.extend(_entry(seed_lists['StaffSeedSaveDataList'],encoded))
                else:
                    encoded=_encode_record('SaveLoadSystem.SeedSaveData',seed)
                    new_seed_payload.extend(_entry(seed_lists['SeedSaveDataList'],encoded))
            seed_changed=True
        next_id+=1
        payload.extend(_entry(item_tag,_encode_record('SaveLoadSystem.ItemData',record)))
        records.append(record)
    updated=_replace_root(data,bag_tag,bytes(payload))
    undo=[{'tag':bag_tag,'before':original_bag['value'],'after':bytes(payload)}]
    if seed_changed:
        current_seed=_root_field(updated,seed_tag)
        seed_payload=(current_seed['value'] if current_seed else b'')+bytes(new_seed_payload)
        updated=_replace_root(updated,seed_tag,seed_payload)
        undo.append({'tag':seed_tag,'before':original_seed['value'] if original_seed else None,'after':seed_payload})
    completed=SCHEMA.decode(updated,'SaveLoadSystem.GameSaveData')
    if completed['BagSaveData']['ItemDataList'][-len(records):]!=records:
        raise ValueError('新增背包记录核对未通过，未写入存档。')
    seed_section=completed.get('AllSeedSaveData',{})
    seed_records=list(seed_section.get('SeedSaveDataList',[]))
    seed_records.extend(row.get('Data',{}) for key in ('HybridSeedSaveDataList','StaffSeedSaveDataList') for row in seed_section.get(key,[]))
    for record in records:
        if not record['SeedLogicID']:continue
        links=[seed for seed in seed_records if seed.get('SeedLogicID')==record['SeedLogicID']]
        if len(links)!=1 or links[0].get('ItemLogicID')!=record['ItemLogicID'] or links[0].get('SeedConfigID')!=record['ConfigId']:
            raise ValueError('新增种子的关联记录核对未通过，未写入存档。')
    if undo_additions(updated,undo)!=original_data:
        raise ValueError('新增物品的反向恢复核对未通过。')
    return updated,undo,records


def undo_additions(data,undo):
    if undo is None:return data
    for section in reversed(undo):
        field=_root_field(data,section['tag'])
        if field is None or field['value']!=section['after']:
            raise ValueError('新增物品的反向恢复位置不匹配。')
        if section['before'] is None:
            data=data[:field['start']]+data[field['end']:]
        else:
            data=replace_payload(data,field,section['before'])
    return data
