"""Generate small, synthetic example data. No installed game or user save is read."""

import json
from pathlib import Path
import struct

APP = Path(__file__).resolve().parent
VERSION = 3


def varint(value):
    value &= (1 << 64) - 1
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def encode_message(name, values, schema):
    result = bytearray()
    for field in schema[name]['fields']:
        if field['name'] not in values or field['protobuf_tag'] is None:
            continue
        value = values[field['name']]
        typ = field['type']
        repeated = typ['kind'] == 'generic'
        if repeated:
            typ = typ['args'][0]
        for element in value if repeated else [value]:
            wire = field['wire_type']
            result.extend(varint(field['protobuf_tag'] * 8 + wire))
            if wire == 0:
                result.extend(varint(int(element)))
            elif wire == 2:
                payload = encode_message(typ['name'], element, schema) if typ['kind'] == 'message' else element.encode('utf-8')
                result.extend(varint(len(payload)))
                result.extend(payload)
            else:
                result.extend(struct.pack('<f' if wire == 5 else '<d', element))
    return bytes(result)


def prepare_demo(destination):
    marker = destination / '.demo-version'
    if marker.is_file() and marker.read_text() == str(VERSION):
        return
    if (destination / 'configs').exists() and not marker.exists():
        raise ValueError('Demo data must use an empty directory, separate from extracted game data.')
    configs = destination / 'configs'
    configs.mkdir(parents=True, exist_ok=True)
    (destination / 'resources').mkdir(exist_ok=True)
    (destination / 'saves').mkdir(exist_ok=True)
    entries = [
        (10000,'小麦种子','Wheat Seed',1,18),(10001,'油菜种子','Rapeseed Seed',1,32),
        (10002,'甜菜种子','Beet Seed',1,8),(10003,'土豆种子','Potato Seed',1,48),
        (10004,'啤酒花种子','Hop Seed',1,12),(10005,'葡萄种子','Grape Seed',1,21),
        (10006,'玉米种子','Corn Seed',1,16),(10007,'防风草种子','Parsnip Seed',1,11),
        (10301,'鸢尾种子','Iris Seed',1,30),(10100,'小麦','Wheat',6,35),
        (10101,'油菜籽','Rapeseed',6,40),(10102,'甜菜','Beet',6,12),
        (10103,'土豆','Potato',6,57),(10104,'啤酒花','Hop',6,15),
        (10105,'葡萄','Grape',6,28),(10106,'玉米','Corn',6,19),
        (10107,'防风草','Parsnip',6,9),(10200,'糖','Sugar',7,25),
        (10201,'油','Oil',7,7),(10509,'石头','Stone',6,60),
        (10202,'面粉','Flour',7,13),(10401,'鸢尾','Iris',6,15),
        (10403,'铁矿草','Ironwort',6,20),(12000,'配方手册','Recipe Book',12,1),
        (10510,'铜锭','Copper Ingot',10,2),(11000,'铜矿石','Copper Ore',10,7),
    ]
    catalogue_only=[(10511,'铁锭','Iron Ingot',10,0),(10512,'金锭','Gold Ingot',10,0)]
    items = []
    for ident, name, english, category, count in entries+catalogue_only:
        items.append({'id':ident,'name':name,'name_en':english,
                      'description':f'{name}。这是一条合成演示记录，用于体验物品搜索、收藏和存档调整。',
                      'raw':{'bnog':ident,'bnoh':ident*10+1,'bnoi':ident*10+2,'bnoj':category,
                             'bnok':1 if category==12 else 9999,'bnol':1,'bnov':f'Assets/Demo/Icon_{ident}'}})
    npcs = [(1001,'丽卡妲',1),(1003,'茜茜',2),(1004,'奈奈',0),(1005,'老金',3),
            (1006,'莫娜',1),(1007,'韩赛尔',2),(1008,'费恩',0),(1009,'卢卡',1),(1010,'乌鹊',0)]
    levels = [0,100,240,420,640,900,1200,1560,1960,2400,2900,3500,4400]
    npc_rows = [{'bnin':ident,'bnio':list(range(len(levels))),'bnip':levels} for ident,_,_ in npcs]
    tools = [{'bodm':tool*100+level,'bodn':tool,'bodt':area}
             for tool in range(1,5) for level,area in enumerate(([1,1],[1,3],[3,3],[5,5]),1)]
    tables = {
        'ItemConfig':[item['raw'] for item in items],
        'FavorNPCConfig':npc_rows,
        'ToolUpgradeConfig':tools,
        'AlchemyLevelConfig':[{'bmyp':i,'bmyq':(i-1)*12} for i in range(1,11)],
        'RecipeConfig':[{'bnwq':5000,'bnwt':'演示配方 · 面粉','bnwu':[10100],'bnwv':[2],'bnww':10202}],
    }
    index=[]
    for name, rows in tables.items():
        ids=[next(iter(row.values())) for row in rows]
        document={'table':name,'count':len(rows),'schema_type':'Example.'+name,'ids':ids,'rows':rows,'demo':True}
        (configs/(name+'.json')).write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8')
        index.append({'table':name,'count':len(rows),'schema_type':document['schema_type'],'unknown_top_level_fields':0})
    friendly={'UnitConfig':[{'id':ident,'name':name,'raw':{}} for ident,name,_ in npcs]}
    for filename, data in [('物品目录.json',items),('分类目录.json',friendly),('index.json',{
        'table_count':len(index),'row_count':sum(x['count'] for x in index),'item_count':len(items),
        'language_entries':0,'tables':index,'demo':True})]:
        (configs/filename).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    (destination/'resources/summary.json').write_text(json.dumps({'bundles':0,'serialized_objects':0,'demo':True}),encoding='utf-8')
    raw_schema=json.loads((APP/'schemas/thepiper-2026-09-25/save_schema.json').read_text(encoding='utf-8'))
    schema={row['name']:row for row in raw_schema['types']}
    save={
        'SlotIdx':0,'TimeStamp':1790503200,'GameTimeStamp':36000,'LoopTime':0,'HasContent':True,'MapId':303,
        'AllAttributeSaveData':{'AttributeParams':[{'AttributeId':901,'Value':128500000},{'AttributeId':902,'Value':240}]},
        'BagSaveData':{'ItemDataList':[{'ConfigId':ident,'Count':count,'Timestamp':0,'SeedLogicID':0,
                    'OriginalSeedItemID':-1,'ItemLogicID':i+1} for i,(ident,_,_,_,count) in enumerate(entries)]},
        'AlchemySaveData':{'Level':3,'TalentPoint':8,'Exp':18,'LastGetExp':0,'LastLevel':3,
                           'AlchemyPrecipitatesValueList':[240],'AlchemyPrecipitatesNumList':[1]},
        'AllFavorData':{'allNPCData':[{'npcID':ident,'favorValue':levels[level],'receiveGiftsToday':1,
                         'currentReturnGiftIndex':-1,'receivedGiftFlag':False,'timeSkipFlag':False} for ident,_,level in npcs]},
        'AllOprToolSaveData':{'OprToolDataList':[{'ID':ident,'Level':0,'SelectedIndex':0} for ident in range(5)]},
        'AllStaffSaveData':{'StaffList':[{'LogicID':i+1,'UnitConfigID':ident,'StaffConfigID':ident,'UnitLogicID':0,
                         'Name':name,'CurrentSan':value,'MaxSan':100,'SanCostPerTick':1,'LastSanUpdateTime':36000,
                         'CurrentWorkID':-1,'State':1} for i,(ident,name,value) in enumerate([(1003,'演示店员',32),(1004,'演示园丁',65),(1005,'演示助手',80)])]},
        'AllBlackJackData':{'BlackJackChips':80},
        'AllMapSaveData':{'FarmMapList':[{'FarmMapIsInitial':True,'MapAreaList':[{'MapAreaID':101,'LogicID':1,
          'ClutterBuildingDataList':[{'Building':{'ConfigID':701,'LogicID':i+1,'Row':i,'Col':2},'CurrentDurability':15000} for i in range(4)]}]}]},
    }
    target=destination/'saves/SAVE_PIPER_0.bytes'
    if not target.exists():
        target.write_bytes(encode_message('SaveLoadSystem.GameSaveData',save,schema))
    elif marker.is_file() and marker.read_text() in ('1','2'):
        # Add a fresh fixture alongside an existing demo; keep the user's edited copy.
        for slot in range(1,100):
            fixture=destination/'saves'/f'SAVE_PIPER_{slot}.bytes'
            if not fixture.exists():
                save['SlotIdx']=slot
                fixture.write_bytes(encode_message('SaveLoadSystem.GameSaveData',save,schema))
                break
    marker.write_text(str(VERSION))
