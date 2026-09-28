"""Validated numeric favor targets, independent of paths and application state.

The native NPC level lookup compares the saved favor value directly with each
threshold; thresholds are absolute totals, not amounts to add per level. Story
gates can hold the displayed game level below this numeric target. This module
therefore plans only favorValue edits and never completes a story or reward.
"""

from collections import Counter
import re

INT32_MAX = 2147483647
NPC_ID_PATH = re.compile(r'AllFavorData\.allNPCData\[\d+\]\.npcID')
NATIVE_NOTE = '已按每位角色的配置计算好感数值。剧情门槛、对话与好感奖励仍需回游戏完成。'


def integer(value, minimum=0):
    return type(value) is int and minimum <= value <= INT32_MAX


def validate(config):
    """Keep table ordering; invalid or ambiguous thresholds are never repaired."""
    if not isinstance(config, dict):
        return {'supported': False, 'reason': '没有这位角色的好感配置', 'levels': []}
    levels, values = config.get('bnio'), config.get('bnip')
    reason = ''
    if not isinstance(levels, list) or not isinstance(values, list) or not levels or len(levels) != len(values):
        reason = '好感档位与数值配置不完整'
    elif not all(integer(x) for x in levels + values):
        reason = '好感配置含有无效整数或超出范围的数值'
    elif levels[0] != 0 or values[0] != 0:
        reason = '好感配置缺少有效的初始档位'
    elif any(a >= b for a, b in zip(levels, levels[1:])) or any(a >= b for a, b in zip(values, values[1:])):
        reason = '好感档位或数值未按递增顺序排列'
    if reason:
        return {'supported': False, 'reason': reason, 'levels': []}
    return {'supported': True, 'reason': '',
            'levels': [{'level': level, 'value': value} for level, value in zip(levels, values)],
            'max_level': levels[-1], 'max_value': values[-1]}


def catalog(rows):
    """A duplicate NPC config is ambiguous, even when the two rows agree."""
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not integer(row.get('bnin'), 1):
            continue
        ident = str(row['bnin'])
        result[ident] = ({'supported': False, 'reason': '存在重复角色好感配置', 'levels': []}
                         if ident in result else validate(row))
    return result


def level_parameter(configs):
    """Derive the slider limit and chips from the loaded table, with no level cap."""
    levels = sorted({entry['level'] for config in configs.values() if config['supported']
                     for entry in config['levels'] if entry['level'] > 0})
    maximum = max(levels, default=0)
    default = max((level for level in levels if level <= 5), default=maximum)
    choices = sorted(set([level for level in (3, 5, 8) if level in levels] + ([maximum] if levels else [])))
    return {'label': '目标数值档位', 'default': default, 'min': min(levels, default=0),
            'max': maximum, 'choices': choices, 'unit': '级'}


def plan(values, configs, target_level=None):
    """Return only existing, uniquely identified, validated NPC value targets."""
    if target_level is not None and not integer(target_level):
        raise ValueError('好感目标档位需要非负整数。')
    records = [(route.rsplit('.', 1)[0], ident) for route, ident in values.items() if NPC_ID_PATH.fullmatch(route)]
    counts = Counter(ident for _, ident in records if integer(ident, 1))
    targets, excluded = [], []
    for parent, ident in records:
        path = parent + '.favorValue'
        current = values.get(path)
        config = configs.get(str(ident))
        reason = ''
        if not integer(ident, 1):
            reason = '角色编号无效'
        elif counts[ident] > 1:
            reason = '存档含有重复角色记录'
        elif config is None:
            reason = '没有这位角色的好感配置'
        elif not config['supported']:
            reason = config['reason']
        elif path not in values:
            reason = '存档缺少好感数值字段'
        elif not integer(current):
            reason = '当前好感数值超出支持范围'
        if reason:
            excluded.append({'id': ident, 'path': path, 'reason': reason})
            continue
        eligible = config['levels'] if target_level is None else [entry for entry in config['levels'] if entry['level'] <= target_level]
        selected = eligible[-1]
        targets.append({'id': ident, 'path': path, 'before': current,
                        'value': max(current, selected['value']), 'target_level': selected['level'],
                        'maximum': config['max_value'], 'max_level': config['max_level']})
    return {'targets': targets, 'excluded': excluded}
