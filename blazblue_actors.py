"""Read character ownership and prepare costs for the native unlock flow."""

import json

from app_paths import APP_ROOT
from blazblue_codec import field, wire_fields


def _map(data):
    result={}
    for entry in wire_fields(data):
        if entry['tag']!=1:
            continue
        if entry['wire']!=2:
            raise ValueError('角色或兑换记录格式无效。')
        key=field(entry['value'],1,0)['value']
        value=field(entry['value'],2,2)['value']
        if key in result:
            raise ValueError('角色或兑换记录包含重复编号。')
        result[key]=value
    return result


def _scalar(data,tag):
    entries=[row for row in wire_fields(data) if row['tag']==tag]
    if not entries:
        return 0
    if len(entries)!=1 or entries[0]['wire']!=0:
        raise ValueError('角色或兑换记录的字段结构无效。')
    return entries[0]['value']


def overview(models, fields):
    catalogue=json.loads((APP_ROOT/'schemas/blazblue/actors.json').read_text(encoding='utf-8'))
    if 'ModelPlayerNewBaseActorPack' not in models or 'ModelPlayerNewExtraState' not in models:
        return {'actors':[],'actor_plan':{'targets':{},'message':'本存档缺少角色或兑换模型，暂未开放角色准备。'}}
    owned=_map(field(models['ModelPlayerNewBaseActorPack'],1,2)['value'])
    for ident,value in owned.items():
        if _scalar(value,1)!=ident:
            raise ValueError('角色记录的编号不一致。')
    calls=_map(field(models['ModelPlayerNewExtraState'],1,2)['value'])
    available={row['id']:row for row in fields}
    rows=[];costs={};missing=set();eligible=0
    for actor in catalogue:
        ident=actor['id'];key=actor['cost_target'];present=ident in owned
        row={**actor,'owned':present,'quantity':available.get(key,{}).get('value',0)}
        if present:
            row.update(status='已解锁（存档记录）',detail='游戏读档时仍会检查内容可用性。' if actor['kind']=='DLC' else '角色已存在，保留原有记录。')
        elif actor['kind']=='DLC':
            row.update(status='需游戏确认 DLC',detail='此角色需要对应 DLC；内容可用后由游戏初始化角色。')
        elif _scalar(calls.get(ident,b''),1)>=1:
            row.update(status='需在游戏内核对',detail='已有一次兑换记录，但缺少角色记录。不会清除兑换历史或重复发放角色。')
        else:
            eligible+=1
            if key not in available:
                missing.add(key)
                row.update(status='缺少解析器记录',detail='先在游戏中取得对应解析器，再重新读取存档。')
            else:
                costs[key]=costs.get(key,0)+actor['cost_count']
                row.update(status='可准备解析资源',detail='补足资源后，回游戏选择该角色并执行原生解析。联动剧情和关卡保持原样。' if actor['kind']=='联动' else '补足解析器后，回游戏选择该角色并执行原生解析。')
        rows.append(row)
    targets={key:max(count,available[key]['value']) for key,count in costs.items()}
    requirements=[{'target':key,'label':available[key]['label'],'required':count,'owned':available[key]['value'],
                   'missing':max(0,count-available[key]['value'])} for key,count in costs.items()]
    owned_count=sum(row['owned'] for row in rows)
    message=(f'存档已记录 {owned_count} / {len(rows)} 位角色。'
             +('可准备剩余普通与联动角色所需的解析资源，最后一步在游戏中完成。' if eligible else '普通与联动角色均已记录，或需要先在游戏中核对异常记录。'))
    return {'actors':rows,'actor_plan':{'targets':targets,'requirements':requirements,'missing_records':sorted(missing),
                                     'owned':owned_count,'total':len(rows),'message':message}}
