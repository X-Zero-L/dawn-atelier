"""Exercise computed favor targets using synthetic configurations and saves."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import favor


def config(ident=1001, levels=None, values=None):
    return {'bnin': ident, 'bnio': [0, 1, 2] if levels is None else levels,
            'bnip': [0, 100, 240] if values is None else values}


def records(*entries):
    result = {}
    for index, (ident, value) in enumerate(entries):
        parent = f'AllFavorData.allNPCData[{index}]'
        result[parent + '.npcID'] = ident
        result[parent + '.favorValue'] = value
        result[parent + '.giftAwarded[0]'] = 17
        result[parent + '.favorLevelGiftIndexFinished[0]'] = 1
    return result


class FavorTargets(unittest.TestCase):
    def test_absolute_thresholds_are_not_summed(self):
        result = favor.plan(records((1001, 30)), favor.catalog([config()]))
        self.assertEqual(result['targets'][0]['value'], 240)
        self.assertNotEqual(result['targets'][0]['value'], 340)

    def test_each_npc_uses_its_own_maximum(self):
        configs = favor.catalog([config(), config(1002, [0, 1], [0, 50])])
        result = favor.plan(records((1001, 30), (1002, 0)), configs)
        self.assertEqual([x['value'] for x in result['targets']], [240, 50])
        self.assertEqual([x['max_level'] for x in result['targets']], [2, 1])

    def test_maximum_and_parameter_can_exceed_level_twelve(self):
        configs = favor.catalog([config(levels=[0, 1, 20], values=[0, 200, 17000])])
        self.assertEqual(favor.level_parameter(configs)['max'], 20)
        self.assertIn(20, favor.level_parameter(configs)['choices'])
        self.assertEqual(favor.plan(records((1001, 0)), configs)['targets'][0]['value'], 17000)

    def test_higher_current_values_are_retained(self):
        result = favor.plan(records((1001, 900)), favor.catalog([config()]))
        self.assertEqual(result['targets'][0]['value'], 900)

    def test_unknown_npc_is_skipped_without_creating_a_record(self):
        result = favor.plan(records((9999, 0)), favor.catalog([config()]))
        self.assertEqual(result['targets'], [])
        self.assertEqual(result['excluded'][0]['reason'], '没有这位角色的好感配置')

    def test_duplicate_config_is_unsupported_even_if_identical(self):
        configs = favor.catalog([config(), config()])
        self.assertFalse(configs['1001']['supported'])
        self.assertEqual(favor.plan(records((1001, 0)), configs)['targets'], [])

    def test_all_duplicate_save_records_are_skipped(self):
        configs = favor.catalog([config(), config(1002)])
        result = favor.plan(records((1001, 0), (1002, 0), (1001, 200)), configs)
        self.assertEqual([x['id'] for x in result['targets']], [1002])
        self.assertEqual(len(result['excluded']), 2)
        self.assertTrue(all('重复' in x['reason'] for x in result['excluded']))

    def test_bad_threshold_tables_are_not_silently_repaired(self):
        bad = [
            config(levels=[], values=[]), config(values=[0, 100]),
            config(levels=[0, 2, 1]), config(levels=[0, 1, 1]),
            config(values=[0, 100, 90]), config(values=[0, 100, 100]),
            config(values=[0, 100, True]), config(values=[0, 100, 1.5]),
            config(values=[0, 100, favor.INT32_MAX + 1]),
            config(values=[0, -1, 100]), config(levels=[1, 2], values=[0, 100]),
            config(values=[5, 100, 240]), {}, None,
        ]
        for entry in bad:
            with self.subTest(config=entry):
                self.assertFalse(favor.validate(entry)['supported'])

    def test_missing_value_field_is_reported_and_not_created(self):
        values = {'AllFavorData.allNPCData[0].npcID': 1001}
        result = favor.plan(values, favor.catalog([config()]))
        self.assertEqual(result['targets'], [])
        self.assertIn('缺少', result['excluded'][0]['reason'])

    def test_invalid_current_values_are_preserved(self):
        for value in (-1, True, 1.5, '100', favor.INT32_MAX + 1):
            with self.subTest(value=value):
                result = favor.plan(records((1001, value)), favor.catalog([config()]))
                self.assertEqual(result['targets'], [])
                self.assertIn('范围', result['excluded'][0]['reason'])

    def test_invalid_id_is_reported(self):
        result = favor.plan(records((True, 0)), favor.catalog([config()]))
        self.assertEqual(result['targets'], [])
        self.assertEqual(result['excluded'][0]['reason'], '角色编号无效')

    def test_level_targets_follow_sparse_configured_labels(self):
        configs = favor.catalog([config(levels=[0, 3, 10])])
        self.assertEqual(favor.plan(records((1001, 0)), configs, 5)['targets'][0]['value'], 100)
        self.assertEqual(favor.plan(records((1001, 0)), configs, 99)['targets'][0]['value'], 240)

    def test_plan_edits_only_values_and_does_not_mutate_inputs(self):
        values = records((1001, 20))
        configs = favor.catalog([config()])
        before = copy.deepcopy((values, configs))
        result = favor.plan(values, configs)
        self.assertEqual((values, configs), before)
        self.assertTrue(all(x['path'].endswith('.favorValue') for x in result['targets']))

    def test_empty_catalog_has_no_invented_level_limit(self):
        self.assertEqual(favor.level_parameter({})['max'], 0)
        self.assertEqual(favor.plan({}, {})['targets'], [])

    def test_preset_roundtrip_preserves_story_rewards_and_unknown_bytes(self):
        # A separate process keeps the fixture isolated from any other test's
        # app_config imports and never resolves the user's real save directory.
        script = '''
import copy, json
import favor, presets, demo_data
from app_config import SAVE_DIR
from save_codec import Schema, encode_varint
schema = Schema()
source = (SAVE_DIR / 'SAVE_PIPER_0.bytes').read_bytes()
unknown = encode_varint(900 << 3) + encode_varint(654321)
source += unknown
path = 'AllFavorData.allNPCData[0].favorValue'
source = schema.edit(source, path, 12000)
before = schema.decode(source, 'SaveLoadSystem.GameSaveData')
result = presets.plan(source, [{'id':'favor_max'}])
assert result['count'] > 0
assert all(x['path'].endswith('.favorValue') for x in result['edits'])
assert favor.NATIVE_NOTE in result['notes']
assert presets.catalog()['npc_favor']['1001']['max_value'] == 4400
assert any(x['id'] == 'social-max' for x in presets.catalog()['bundles'])
changed = source
for edit in result['edits']:
    changed = schema.edit(changed, edit['path'], int(edit['value']))
after = schema.decode(changed, 'SaveLoadSystem.GameSaveData')
assert after['AllFavorData']['allNPCData'][0]['favorValue'] == 12000
assert all(x['favorValue'] >= presets.NPC_FAVOR[str(x['npcID'])]['max_value'] for x in after['AllFavorData']['allNPCData'])
assert presets.plan(changed, [{'id':'favor_max'}])['count'] == 0
for left, right in zip(before['AllFavorData']['allNPCData'], after['AllFavorData']['allNPCData']):
    right['favorValue'] = left['favorValue']
assert before == after, 'A story, reward, or unrelated field changed.'
assert changed.endswith(unknown)
values = {x['path']:x['value'] for x in schema.leaves(source)}
for edit in reversed(result['edits']):
    changed = schema.edit(changed, edit['path'], values[edit['path']])
assert changed == source, 'Reverse edits must recover the exact input bytes.'
custom = favor.catalog([{'bnin':1001,'bnio':[0,1,20],'bnip':[0,200,17000]}])
presets.NPC_FAVOR = custom
presets.ACTION_BY_ID['favor']['parameter'] = favor.level_parameter(custom)
assert presets.normalize_actions([{'id':'favor','value':20}])[0]['value'] == 20
result = presets.plan(source, [{'id':'favor_max'}])
assert len(result['favor_exclusions']) == 8
assert result['count'] == 1
assert result['edits'][0]['value'] == '17000'
print(json.dumps({'changes':len(values),'status':'ok'}))
'''
        with tempfile.TemporaryDirectory(prefix='dawn-favor-check-') as directory:
            env = {**os.environ, 'DAWN_HOME': directory, 'DAWN_DATA_DIR': str(Path(directory) / 'data'), 'DAWN_DEMO': '1'}
            result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                                    env=env, text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
