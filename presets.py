"""Allowlisted preset recipes that plan byte-preserving edits to existing save fields."""

import json
from pathlib import Path
import re

from save_codec import ROOT, Schema
from app_config import DATA_ROOT, SCHEMA_ROOT

SCHEMA = Schema()


def rows(name):
    return json.loads((DATA_ROOT / 'configs' / (name + '.json')).read_text(encoding='utf-8'))['rows']


ITEM_CONFIG = {x['bnog']: x for x in rows('ItemConfig')}
ITEM_NAMES = {x['id']: x['name'] for x in json.loads((DATA_ROOT / 'configs/物品目录.json').read_text(encoding='utf-8'))}
NPC_CONFIG = {x['bnin']: x for x in rows('FavorNPCConfig')}
TOOL_CONFIG = {}
for row in rows('ToolUpgradeConfig'):
    if row.get('bodn') in (1, 2, 3, 4) and row.get('bodm', 0) > 0:
        TOOL_CONFIG.setdefault(row['bodn'], []).append(row)
TOOL_NAMES = {1: '播种工具', 2: '浇水工具', 3: '收获工具', 4: '铲除工具'}
SUPPLY_TYPES = {1, 2, 3, 4, 5, 6, 7, 8, 9, 15}


def number(label, default, minimum, maximum, choices=None, unit=''):
    return {'label': label, 'default': default, 'min': minimum, 'max': maximum,
            'choices': choices or [], 'unit': unit}


ACTIONS = [
    {'id':'gold','name':'备足金币','category':'财富','icon':'coin','description':'将持有金币补足到目标，余额更高时保留。','parameter':number('目标金币',1000000,0,999999999,[100000,1000000,10000000],'金币')},
    {'id':'inventory','name':'背包补给','category':'背包','icon':'bag','description':'补足已有的可堆叠日常物品，保留任务物品和独特道具。','parameter':number('每组至少',99,1,9999,[30,99,999],'个')},
    {'id':'seeds','name':'种子储备','category':'背包','icon':'sprout','description':'补足已有作物、炼金、杂交与员工种子。','parameter':number('每组至少',99,1,9999,[30,99,999],'个')},
    {'id':'materials','name':'材料储备','category':'背包','icon':'layers','description':'补足已有材料，方便制作和建造。','parameter':number('每组至少',99,1,9999,[30,99,999],'个')},
    {'id':'products','name':'商品备货','category':'经营','icon':'archive','description':'补足已有商品、产物与珍品，省去逐格修改。','parameter':number('每组至少',99,1,9999,[30,99,999],'个')},
    {'id':'fertilizer','name':'肥料储备','category':'种植','icon':'sprout','description':'补足背包里已经拥有的肥料。','parameter':number('每组至少',99,1,9999,[30,99,999],'个')},
    {'id':'talent','name':'炼金天赋点','category':'成长','icon':'flask','description':'补足可用天赋点，供你在游戏里自由选择天赋。','parameter':number('可用点数',30,0,999,[10,30,100],'点')},
    {'id':'favor','name':'好感进阶','category':'社交','icon':'heart','description':'按每位 NPC 自己的档位配置提升好感，较高好感会保留。','note':'调整好感数值；后续剧情与奖励沿用游戏规则。','parameter':number('目标档位',5,1,12,[3,5,8,12],'级')},
    {'id':'gifts','name':'重置今日送礼','category':'社交','icon':'heart','description':'把已有 NPC 记录的今日收礼次数归零。'},
    {'id':'staff','name':'员工恢复精神','category':'经营','icon':'users','description':'将员工当前 SAN 恢复到各自上限；零上限员工保持原设定。'},
    {'id':'tools','name':'升级农用工具','category':'种植','icon':'tool','description':'升级播种、浇水、收获和铲除工具，并选中该级可用范围。','parameter':number('目标等级',4,1,4,[2,3,4],'级')},
    {'id':'clutter','name':'轻松清理杂物','category':'种植','icon':'tool','description':'将已有杂物的剩余耐久降到 1，下次正常清理时由游戏处理掉落。'},
    {'id':'chips','name':'牌桌筹码','category':'娱乐','icon':'star','description':'补足存档中的二十一点筹码。','parameter':number('目标筹码',1000,0,1000000,[100,1000,10000],'枚')},
]
ACTION_BY_ID = {x['id']: x for x in ACTIONS}
BUNDLES = [
    {'id':'starter','name':'轻松开荒','subtitle':'从容出发，慢慢探索','description':'准备启动资金、基础种子和天赋点，给新一天留一点余裕。','category':'推荐','icon':'sun','tone':'sage','art':10000,'badge':'推荐入门','actions':[{'id':'gold','value':100000},{'id':'seeds','value':30},{'id':'talent','value':10}]},
    {'id':'farmer','name':'田园日常','subtitle':'少些重复，多些收获','description':'种子与肥料补给，农具满级，顺手减轻清理杂物的负担。','category':'种植','icon':'sprout','tone':'olive','art':10003,'actions':[{'id':'seeds','value':99},{'id':'fertilizer','value':99},{'id':'tools','value':4},{'id':'clutter'}]},
    {'id':'merchant','name':'富足经营','subtitle':'让店铺和行囊都充实','description':'补足一百万金币和日常货品，让员工以充足精神继续工作。','category':'经营','icon':'bag','tone':'gold','art':10201,'actions':[{'id':'gold','value':1000000},{'id':'inventory','value':99},{'id':'staff'}]},
    {'id':'alchemist','name':'炼金准备','subtitle':'为下一次灵感备好材料','description':'材料、炼金种子与天赋点一次准备，配方依然由你选择。','category':'成长','icon':'flask','tone':'lilac','art':10509,'actions':[{'id':'materials','value':99},{'id':'seeds','value':99},{'id':'talent','value':30}]},
    {'id':'social','name':'街坊好友','subtitle':'给每一次相遇一点温度','description':'将现有 NPC 的好感提升到第 5 档，并恢复今日送礼次数。','category':'社交','icon':'heart','tone':'rose','art':10401,'actions':[{'id':'favor','value':5},{'id':'gifts'}]},
    {'id':'collector','name':'充实储备','subtitle':'把准备工作一次做好','description':'补足千万金币、999 份日常补给与 1000 枚牌桌筹码。','category':'进阶','icon':'archive','tone':'sand','art':10106,'actions':[{'id':'gold','value':10000000},{'id':'inventory','value':999},{'id':'chips','value':1000}]},
]


def catalog():
    return {'version':1,'actions':ACTIONS,'bundles':BUNDLES,
            'npc_levels':{str(ident):[{'level':level,'value':value} for level,value in zip(config.get('bnio',[]),config.get('bnip',[]))] for ident,config in NPC_CONFIG.items()},
            'tool_ranges':{str(ident):[row.get('bodt',[1,1]) for row in sorted(config,key=lambda row:row['bodm'])] for ident,config in TOOL_CONFIG.items()},
            'rules':['只调整存档中已有记录','补足操作保留更高现值','物品数量受配置上限约束','方案可预览、撤销和保存']}


def normalize_actions(actions):
    if not isinstance(actions, list) or not 1 <= len(actions) <= len(ACTIONS):
        raise ValueError('请选择至少一项配置。')
    result=[]
    seen=set()
    for item in actions:
        if not isinstance(item, dict) or item.get('id') not in ACTION_BY_ID or item['id'] in seen:
            raise ValueError('方案含有未知或重复的操作。')
        ident=item['id'];seen.add(ident);definition=ACTION_BY_ID[ident]
        if 'parameter' in definition:
            raw=item.get('value',definition['parameter']['default'])
            if isinstance(raw,bool) or not re.fullmatch(r'\d+',str(raw)):
                raise ValueError(definition['name']+'需要整数目标。')
            value=int(raw);parameter=definition['parameter']
            if not parameter['min'] <= value <= parameter['max']:
                raise ValueError(f"{definition['name']}的范围为 {parameter['min']} 至 {parameter['max']}。")
            result.append({'id':ident,'value':value})
        else:
            result.append({'id':ident})
    return result


def plan(data, actions):
    requested=normalize_actions(actions)
    values={field['path']:field['value'] for field in SCHEMA.leaves(data)}
    changes={}
    reports=[]
    skipped=[]

    def old(route):
        return changes[route]['raw_value'] if route in changes else values[route]

    def update(route, value, action, report, label, detail='', scale=1):
        if route not in values:
            return
        report['matched']+=1
        if old(route)==value:
            report['unchanged']+=1
            return
        report['changed']+=1
        changes[route]={'path':route,'raw_value':value,'value':str(value//scale) if scale!=1 else str(value),
                        'before':str(values[route]//scale) if scale!=1 else str(values[route]),
                        'label':label,'detail':detail,'action':action,'scale':scale}

    for action in requested:
        ident=action['id'];target=action.get('value');definition=ACTION_BY_ID[ident]
        report={'id':ident,'name':definition['name'],'matched':0,'changed':0,'unchanged':0,'excluded':0}
        if ident=='gold':
            for route, value in values.items():
                if re.fullmatch(r'AllAttributeSaveData\.AttributeParams\[\d+\]\.AttributeId',route) and value==901:
                    amount=route.rsplit('.',1)[0]+'.Value'
                    if amount in values:update(amount,max(old(amount),target*1000),ident,report,'金币','持有金币',1000)
        elif ident in ('inventory','seeds','materials','products','fertilizer'):
            allowed={'inventory':SUPPLY_TYPES,'seeds':{1,2,3,15},'materials':{6},'products':{5,7,8},'fertilizer':{9}}[ident]
            for route, config_id in values.items():
                if not re.fullmatch(r'BagSaveData\.ItemDataList\[\d+\]\.ConfigId',route):continue
                config=ITEM_CONFIG.get(config_id,{})
                if config.get('bnoj') not in allowed:continue
                count=route.rsplit('.',1)[0]+'.Count';cap=config.get('bnok',0)
                if count not in values or cap<=1:
                    report['excluded']+=1;continue
                amount=max(old(count),min(target,cap))
                update(count,amount,ident,report,'数量',ITEM_NAMES.get(config_id,f'物品 {config_id}'))
        elif ident=='talent':
            route='AlchemySaveData.TalentPoint'
            if route in values:update(route,max(old(route),target),ident,report,'天赋点','炼金成长')
        elif ident in ('favor','gifts'):
            for route,npc_id in values.items():
                if not re.fullmatch(r'AllFavorData\.allNPCData\[\d+\]\.npcID',route):continue
                parent=route.rsplit('.',1)[0]
                if ident=='gifts':
                    field=parent+'.receiveGiftsToday'
                    if field in values and old(field)>=0:update(field,0,ident,report,'今日收礼次数',f'NPC {npc_id}')
                else:
                    config=NPC_CONFIG.get(npc_id,{})
                    thresholds=list(zip(config.get('bnio',[]),config.get('bnip',[])))
                    field=parent+'.favorValue'
                    if not thresholds or field not in values:report['excluded']+=1;continue
                    eligible=[pair for pair in thresholds if pair[0]<=target]
                    threshold=max(eligible,key=lambda pair:pair[0])[1] if eligible else thresholds[0][1]
                    update(field,max(old(field),threshold),ident,report,'好感值',f'NPC {npc_id}')
        elif ident=='staff':
            for route,maximum in values.items():
                if not re.fullmatch(r'AllStaffSaveData\.StaffList\[\d+\]\.MaxSan',route):continue
                parent=route.rsplit('.',1)[0];current=parent+'.CurrentSan'
                if maximum<=0 or current not in values:report['excluded']+=1;continue
                update(current,max(old(current),maximum),ident,report,'当前 SAN',values.get(parent+'.Name','员工'))
        elif ident=='tools':
            for route,tool_id in values.items():
                if not re.fullmatch(r'AllOprToolSaveData\.OprToolDataList\[\d+\]\.ID',route) or tool_id not in TOOL_CONFIG:continue
                parent=route.rsplit('.',1)[0];level=parent+'.Level';selected=parent+'.SelectedIndex'
                if level not in values:continue
                maximum=len(TOOL_CONFIG[tool_id])-1
                if not 0<=old(level)<=maximum:report['excluded']+=1;continue
                target_level=max(old(level),min(target-1,maximum))
                update(level,target_level,ident,report,'工具等级（从 0 计）',TOOL_NAMES[tool_id])
                if selected in values:update(selected,target_level,ident,report,'使用范围档位',TOOL_NAMES[tool_id])
        elif ident=='clutter':
            for route,value in values.items():
                if re.search(r'\.ClutterBuildingDataList\[\d+\]\.CurrentDurability$',route) and value>0:
                    update(route,min(old(route),1),ident,report,'剩余耐久','地图杂物')
        elif ident=='chips':
            route='AllBlackJackData.BlackJackChips'
            if route in values:update(route,max(old(route),target),ident,report,'筹码','二十一点')
        if report['changed']==0:
            reason='当前数值已满足目标' if report['matched'] else '当前存档没有适用记录'
            if ident=='staff' and report['excluded']:reason='已有员工的 SAN 上限为 0，保留其特殊设定'
            report['message']=reason
            skipped.append({'action':definition['name'],'reason':reason})
        else:
            report['message']=f"{report['changed']} 项调整"+(f"，{report['unchanged']} 项已满足" if report['unchanged'] else '')
        reports.append(report)
    # Omit net no-ops when two requested actions converge on the original value.
    changes={route:change for route,change in changes.items() if change['raw_value']!=values[route]}
    return {'actions':requested,'edits':[{'path':change['path'],'value':change['value']} for change in changes.values()],
            'changes':[{key:value for key,value in change.items() if key!='raw_value'} for change in changes.values()],
            'count':len(changes),'reports':reports,'skipped':skipped}
