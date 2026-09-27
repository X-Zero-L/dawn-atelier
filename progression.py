"""Prepare resources for native progression without writing unlock or rank state."""

from collections import Counter
from functools import lru_cache
import json
import math

from app_config import DATA_ROOT
import inventory
from save_codec import Schema

SCHEMA = Schema()
SHOP_PATH = 'AllMapSaveData.WorkShopMap.ShopSaveData.StatsData'
GOLD_MAX = 999999999000
KINDS = {0: '炼金建筑', 1: '炼金配方', 2: '故事节点', 3: '炼金种子', 4: '能力强化'}


@lru_cache(maxsize=None)
def table(name):
    path = DATA_ROOT / 'configs' / (name + '.json')
    return json.loads(path.read_text(encoding='utf-8'))['rows'] if path.is_file() else []


@lru_cache(maxsize=1)
def definitions():
    friendly_path = DATA_ROOT / 'configs/分类目录.json'
    friendly = json.loads(friendly_path.read_text(encoding='utf-8')) if friendly_path.is_file() else {}
    return {
        'talents': {row['bmzw']: row for row in table('AlchemyTalentConfig')},
        'names': {row['id']: row['name'] for row in friendly.get('AlchemyTalentConfig', [])},
        'groups': {row['bnpb']: row for row in table('ItemGroupConfig')},
        'recipes': {row['bnwq']: row for row in table('RecipeConfig')},
        'ranks': {row['bnzo']: row for row in table('ShopRankConfig')},
        'npcs': {row['bnin']: row for row in table('FavorNPCConfig')},
        'npc_names': {row['id']: row['name'] for row in friendly.get('UnitConfig', [])},
    }


def talent_name(ident):
    config = definitions()
    return config['names'].get(ident) or config['talents'].get(ident, {}).get('bmzz') or f'天赋 {ident}'


def material_cost(talent):
    group_id = talent.get('bnah', 0)
    if not group_id:
        return Counter()
    group = definitions()['groups'].get(group_id)
    if not group or group.get('bnpc') != 1 or group.get('bnpg', 1) != 1:
        raise ValueError('该天赋的材料规则尚未确认，暂不支持自动补齐。')
    items, counts, kinds = group.get('bnpe', []), group.get('bnpf', []), group.get('bnpd', [])
    if not items or not len(items) == len(counts) == len(kinds) or any(kind != 1 for kind in kinds):
        raise ValueError('该天赋的材料结构不受支持。')
    result = Counter()
    for ident, count in zip(items, counts):
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0 or ident not in inventory.ITEM_BY_ID:
            raise ValueError('材料配置缺少有效物品或数量。')
        result[ident] += count
    return result


def snapshot(data):
    decoded = SCHEMA.decode(data, 'SaveLoadSystem.GameSaveData')
    values = {field['path']: field['value'] for field in SCHEMA.leaves(data)}
    stats = decoded.get('AllMapSaveData', {}).get('WorkShopMap', {}).get('ShopSaveData', {}).get('StatsData', {})
    alchemy = decoded.get('AlchemySaveData', {})
    attributes = decoded.get('AllAttributeSaveData', {}).get('AttributeParams', [])
    gold_rows = [(index, row) for index, row in enumerate(attributes) if row.get('AttributeId') == 901]
    gold_path = f'AllAttributeSaveData.AttributeParams[{gold_rows[0][0]}].Value' if len(gold_rows) == 1 else None
    bag = decoded.get('BagSaveData', {}).get('ItemDataList', [])
    counts = Counter()
    for item in bag:
        count = item.get('Count', 0)
        if isinstance(count, int) and count >= 0:
            counts[item.get('ConfigId')] += count
    npcs = decoded.get('AllFavorData', {}).get('allNPCData', [])
    history = decoded.get('StatisticSaveData', {})
    history_items, history_counts = history.get('ItemGetItemList', []), history.get('ItemGetCountList', [])
    obtained = {ident for ident, count in zip(history_items, history_counts) if count > 0} if len(history_items) == len(history_counts) else set()
    return {'decoded': decoded, 'values': values, 'stats': stats, 'alchemy': alchemy, 'bag': bag,
            'owned': counts, 'gold_path': gold_path, 'gold': values.get(gold_path, 0),
            'npcs': npcs, 'favor': sum(row.get('favorValue', 0) for row in npcs),
            'obtained': obtained, 'entry_open': 200207 in decoded.get('AllMissionSaveData', {}).get('FinishedMissionList', []),
            'rank': stats.get('CurrentRank'), 'unlocked': set(alchemy.get('UnlockTalentList', [])),
            'story_active': set(alchemy.get('ActiveStoryTalentList', []))}


def active(ident, state):
    row = definitions()['talents'].get(ident)
    return bool(row and ident in state['unlocked'] and
                (row.get('bnac', 0) != 2 or ident in state['story_active']))


def talent_order(ids, state):
    """Dependencies first; story nodes remain in the game's own event flow."""
    result, done, visiting = [], set(), set()
    def visit(ident):
        if ident in state['unlocked'] or ident in done:
            return
        row = definitions()['talents'].get(ident)
        if row is None:
            raise ValueError('前置天赋配置缺失，请重新准备游戏资料。')
        if ident in visiting:
            raise ValueError('天赋前置关系出现循环，未生成修改。')
        if row.get('bnac', 0) == 2:
            return
        visiting.add(ident)
        for previous in row.get('bnae', []):
            visit(previous)
        visiting.remove(ident)
        done.add(ident)
        if ident not in state['unlocked']:
            result.append(ident)
    for ident in ids:
        visit(ident)
    return result


def blockers(order, state):
    config = definitions()['talents']
    expected = set(order)
    result = [] if state['entry_open'] or not order else ['先在游戏中完成主线“炼金入门”，开放炼金界面。']
    for ident in order:
        row = config[ident]
        required = row.get('bnaa', 0)
        if state['rank'] is None or state['rank'] < required:
            result.append(f'{talent_name(ident)}：需要工坊 Lv.{required}')
        for previous in row.get('bnae', []):
            if previous not in state['unlocked'] and previous not in expected:
                result.append(f'{talent_name(ident)}：先在游戏完成“{talent_name(previous)}”')
        if row.get('bnac', 0) == 1:
            recipe = definitions()['recipes'].get(row.get('bnad'))
            if recipe is None:
                result.append(f'{talent_name(ident)}：配方资料缺失，请重新准备游戏资料')
            else:
                missing = [inventory.ITEM_BY_ID.get(item, {}).get('name', str(item)) for item in recipe.get('bnwu', []) if item not in state['obtained']]
                if missing:
                    result.append(f'{talent_name(ident)}：需在游戏中实际获得原料 ' + '、'.join(missing))
    return list(dict.fromkeys(result))


def rank_requirements(rank, target):
    rows = definitions()['ranks']
    if not rows or rank is None:
        return None
    maximum = max(rows)
    if isinstance(target, bool) or not isinstance(target, int) or not 1 <= target <= maximum:
        raise ValueError(f'目标工坊等级需为 1 至 {maximum}。')
    if not isinstance(rank, int) or rank < 0 or rank > maximum:
        raise ValueError('当前工坊等级超出支持范围。')
    needed = []
    for level in range(max(1, rank), target):
        if level not in rows or level + 1 not in rows:
            raise ValueError('工坊等级配置不连续，未生成修改。')
        needed.append(rows[level])
    return {'income': max((row.get('bnzp', 0) for row in needed), default=0),
            'building': max((row.get('bnzq', 0) for row in needed), default=0),
            'aesthetic': max((row.get('bnzr', 0) for row in needed), default=0),
            'favor': math.ceil(max((row.get('bnzs', 0) for row in needed), default=0) / 1000)}


def overview(data):
    state = snapshot(data)
    config = definitions()
    rank = state['rank']
    rank_max = max(config['ranks'], default=0)
    workshop = {'available': rank is not None and bool(rank_max), 'rank': rank, 'max_rank': rank_max,
                'targets': [], 'note': '在游戏工坊面板点击升级，逐级领取解锁与奖励。建筑和美观按实际布置重新计算。'}
    if workshop['available']:
        for target in range(max(1, rank + 1), rank_max + 1):
            required = rank_requirements(rank, target)
            metrics = [
                {'id': 'income', 'name': '累计营业额', 'current': state['stats'].get('IncomeMetrics', 0) / 1000,
                 'required': required['income'] / 1000, 'editable': True, 'unit': '金币'},
                {'id': 'building', 'name': '建筑价值', 'current': state['stats'].get('BuildingMetrics', 0) / 1000,
                 'required': required['building'] / 1000, 'editable': False, 'unit': '点'},
                {'id': 'aesthetic', 'name': '美观度', 'current': state['stats'].get('AsetheticMetrics', 0) / 1000,
                 'required': required['aesthetic'] / 1000, 'editable': False, 'unit': '点'},
                {'id': 'favor', 'name': '总好感', 'current': state['favor'],
                 'required': required['favor'], 'editable': True, 'unit': '点'},
            ]
            for metric in metrics:
                metric['met'] = metric['current'] >= metric['required']
                metric['gap'] = round(max(0, metric['required'] - metric['current']), 3)
            workshop['targets'].append({'level': target, 'metrics': metrics})
    talents = []
    for ident, row in config['talents'].items():
        kind = row.get('bnac', 0)
        reasons = []
        costs = Counter()
        try:
            costs = material_cost(row)
        except ValueError as error:
            reasons.append(str(error))
        materials = [{'id': item, 'name': inventory.ITEM_BY_ID[item]['name'], 'quantity': count,
                      'owned': state['owned'][item], 'can_add': inventory.addition_supported(inventory.ITEM_BY_ID[item]['raw'])}
                     for item, count in costs.items()]
        if kind != 2 and ident not in state['unlocked']:
            reasons += blockers(talent_order([ident], state), state)
        prerequisites = [{'id': previous, 'name': talent_name(previous), 'active': previous in state['unlocked'],
                          'story': config['talents'].get(previous, {}).get('bnac', 0) == 2}
                         for previous in row.get('bnae', [])]
        resources_ready = (state['gold'] >= row.get('bnag', 0) and
                           state['alchemy'].get('TalentPoint', 0) >= row.get('bnaf', 0) and
                           all(item['owned'] >= item['quantity'] for item in materials))
        talents.append({'id': ident, 'name': talent_name(ident), 'description': row.get('bmzz', ''),
                        'kind': kind, 'kind_name': KINDS.get(kind, '其他'), 'story': kind == 2,
                        'unlocked': ident in state['unlocked'], 'active': active(ident, state),
                        'rank': row.get('bnaa', 0), 'points': row.get('bnaf', 0), 'gold': row.get('bnag', 0) / 1000,
                        'materials': materials, 'prerequisites': prerequisites, 'blockers': list(dict.fromkeys(reasons)),
                        'resources_ready': resources_ready,
                        'ready': kind != 2 and ident not in state['unlocked'] and resources_ready and not reasons and all(x['active'] for x in prerequisites),
                        'can_prepare': kind != 2 and ident not in state['unlocked']})
    return {'workshop': workshop, 'alchemy': {'available': bool(config['talents']), 'entry_open': state['entry_open'], 'talents': talents,
            'unlocked': sum(row['unlocked'] for row in talents), 'total': len(talents),
            'note': '补齐资源后，回到游戏炼金天赋树，按前置顺序点击解锁。故事节点随游戏剧情完成。'}}


def plan(data, kind, target=None, talent_ids=None):
    state = snapshot(data)
    values = state['values']
    changes, blocked, order, notes = {}, [], [], []
    config = definitions()

    def top_up(route, amount, label, detail, scale=1):
        if route not in values:
            raise ValueError(f'存档缺少“{label}”记录，请先在游戏中保存一次。')
        before = values[route]
        if not isinstance(before, int) or isinstance(before, bool) or before < 0:
            raise ValueError(f'{label} 当前数值异常，未生成修改。')
        if before >= amount:
            return
        value = amount
        display = lambda number: format(number / scale, '.3f').rstrip('0').rstrip('.') if scale != 1 else str(number)
        changes[route] = {'path': route, 'raw_value': value, 'value': display(value), 'before': display(before),
                          'label': label, 'detail': detail, 'action': kind, 'scale': scale}

    if kind == 'alchemy':
        if not config['talents'] or not state['alchemy']:
            raise ValueError('当前存档或游戏资料缺少炼金天赋记录，请先准备资料并保存游戏。')
        if talent_ids is None:
            selected = []
            for ident, row in config['talents'].items():
                if row.get('bnac', 0) == 2 or ident in state['unlocked']:
                    continue
                candidate = talent_order([ident], state)
                if not blockers(candidate, state):
                    selected.append(ident)
        else:
            if not isinstance(talent_ids, list) or not 1 <= len(talent_ids) <= len(config['talents']):
                raise ValueError('请选择有效的炼金天赋。')
            if any(isinstance(ident, bool) or not isinstance(ident, int) or ident not in config['talents'] for ident in talent_ids):
                raise ValueError('天赋列表含有未知项目。')
            if len(set(talent_ids)) != len(talent_ids):
                raise ValueError('天赋列表包含重复项目。')
            if any(config['talents'][ident].get('bnac', 0) == 2 for ident in talent_ids):
                raise ValueError('故事节点由游戏剧情完成，请选择普通炼金天赋。')
            selected = talent_ids
        order = talent_order(selected, state)
        blocked = blockers(order, state)
        money, points, materials = 0, 0, Counter()
        for ident in order:
            row = config['talents'][ident]
            money += row.get('bnag', 0)
            points += row.get('bnaf', 0)
            materials.update(material_cost(row))
        if money > GOLD_MAX or points > 2147483647 or money < 0 or points < 0:
            raise ValueError('所选天赋的总成本超出支持范围。')
        if order:
            top_up(state['gold_path'], money, '金币', '炼金解锁所需金币', 1000)
            top_up('AlchemySaveData.TalentPoint', points, '天赋点', '炼金解锁所需点数')
        for ident, needed in materials.items():
            if state['owned'][ident] >= needed:
                continue
            item = inventory.ITEM_BY_ID[ident]
            cap = item['raw'].get('bnok', 0)
            if not inventory.addition_supported(item['raw']) or needed > cap:
                raise ValueError(f'{item["name"]} 无法按当前成本安全补齐。')
            owned = [(i, entry) for i, entry in enumerate(state['bag']) if entry.get('ConfigId') == ident]
            deficit = needed - state['owned'][ident]
            if owned:
                for index, entry in owned:
                    route = f'BagSaveData.ItemDataList[{index}].Count'
                    current = entry.get('Count', 0)
                    addition = min(deficit, max(0, cap - current))
                    if addition:
                        top_up(route, current + addition, '数量', item['name'])
                        deficit -= addition
                    if not deficit:
                        break
                if deficit:
                    raise ValueError(f'{item["name"]} 的现有堆叠无法补齐所需数量。')
            else:
                addition, excluded = inventory.missing_items(data, needed, {ident})
                if len(addition) != 1 or excluded:
                    raise ValueError(f'{item["name"]} 的关联记录无法安全补齐。')
                changes[addition[0]['path']] = {**addition[0], 'action': kind}
        notes.append('资源加入清单后需保存并重新读档；回炼金天赋树按下列顺序点击解锁。')
        if not order:
            notes.append('当前没有可准备的普通天赋；已解锁项目保留，工坊等级和故事前置按游戏要求完成。')
        title = '炼金解锁准备'
    elif kind == 'workshop':
        if state['rank'] is None or not config['ranks']:
            raise ValueError('当前存档没有工坊成长记录，请先在游戏里进入工坊并保存。')
        target = min(state['rank'] + 1, max(config['ranks'])) if target is None else target
        required = rank_requirements(state['rank'], target)
        if target > state['rank']:
            top_up(SHOP_PATH + '.IncomeMetrics', required['income'], '累计营业额', '工坊升级条件', 1000)
            if state['stats'].get('BuildingMetrics', 0) < required['building']:
                blocked.append('建筑价值仍需在游戏中通过实际建造提升。')
            if state['stats'].get('AsetheticMetrics', 0) < required['aesthetic']:
                blocked.append('美观度仍需在游戏中通过实际布置提升。')
            remaining = max(0, required['favor'] - state['favor'])
            candidates, seen = [], set()
            for index, npc in enumerate(state['npcs']):
                ident = npc.get('npcID')
                if ident in seen:
                    raise ValueError('存档含有重复角色好感记录，未生成修改。')
                seen.add(ident)
                current = npc.get('favorValue', 0)
                thresholds = config['npcs'].get(ident, {}).get('bnip', [])
                maximum = max(thresholds, default=current)
                if current >= 0 and maximum > current:
                    candidates.append({'index': index, 'id': ident, 'current': current, 'value': current, 'maximum': maximum})
            while remaining and candidates:
                share = math.ceil(remaining / len(candidates))
                for npc in candidates:
                    addition = min(share, remaining, npc['maximum'] - npc['value'])
                    npc['value'] += addition
                    remaining -= addition
                    if not remaining:
                        break
                for npc in candidates:
                    if npc['value'] > npc['current']:
                        top_up(f'AllFavorData.allNPCData[{npc["index"]}].favorValue', npc['value'], '好感值',
                               config['npc_names'].get(npc['id'], f'角色 {npc["id"]}'))
                candidates = [npc for npc in candidates if npc['value'] < npc['maximum']]
            if remaining:
                blocked.append(f'已有角色按各自好感上限补足后，总好感仍差 {remaining} 点；需在游戏中结识更多角色。')
        notes.append(f'保存并重新读档后，在游戏工坊面板逐级点击升级至 Lv.{target}，领取对应建筑、配方与奖励。')
        notes.append('总好感补足会调整已有角色的好感值，可在修改清单逐项核对。建筑价值和美观度以游戏实际布置为准。')
        if target <= state['rank']:
            notes.append('当前工坊等级已达到目标，本次无需调整。')
        title = '工坊升级准备'
    else:
        raise ValueError('未知的成长准备操作。')
    planned = list(changes.values())
    report = {'id': kind, 'name': title, 'matched': len(planned), 'changed': len(planned), 'unchanged': 0,
              'message': f'{len(planned)} 项资源调整；最终升级与解锁在游戏中完成'}
    return {'changes': planned, 'count': len(planned), 'new_items': sum(row.get('operation') == 'add_item' for row in planned),
            'missing_exclusions': [], 'reports': [report], 'skipped': [], 'notes': notes, 'blockers': blocked,
            'unlock_order': [{'id': ident, 'name': talent_name(ident)} for ident in order], 'kind': kind, 'title': title}
