"""Verify resource preparation and preservation using disposable synthetic saves."""

import copy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

WORKSPACE = tempfile.TemporaryDirectory(prefix='dawn-progression-check-')
os.environ['DAWN_HOME'] = WORKSPACE.name
os.environ['DAWN_DATA_DIR'] = str(Path(WORKSPACE.name) / 'data')
os.environ['DAWN_DEMO'] = '1'

import demo_data
import inventory
import presets
import progression
from app_config import SAVE_DIR, SCHEMA_ROOT
from save_codec import Schema, encode_varint
import web_server

SCHEMA = Schema()
BASE = (SAVE_DIR / 'SAVE_PIPER_0.bytes').read_bytes()


def apply_plan(data, plan):
    original = data
    scalars = []
    additions = []
    values = {field['path']: field['value'] for field in SCHEMA.leaves(data)}
    for change in plan['changes']:
        if change.get('operation') == 'add_item':
            additions.append(change)
        else:
            data = SCHEMA.edit(data, change['path'], change['raw_value'])
            scalars.append(change)
    data, undo, _ = inventory.append_items(data, additions)
    reverted = inventory.undo_additions(data, undo)
    for change in reversed(scalars):
        reverted = SCHEMA.edit(reverted, change['path'], values[change['path']])
    if reverted != original:
        raise AssertionError('Reverse edit did not restore the exact source bytes.')
    return data


def alter_document(data, change):
    document = SCHEMA.decode(data, 'SaveLoadSystem.GameSaveData')
    change(document)
    schema = {row['name']: row for row in __import__('json').loads((SCHEMA_ROOT / 'save_schema.json').read_text(encoding='utf-8'))['types']}
    return demo_data.encode_message('SaveLoadSystem.GameSaveData', document, schema)


class ProgressionPreparation(unittest.TestCase):
    def setUp(self):
        (SAVE_DIR / 'SAVE_PIPER_0.bytes').write_bytes(BASE)

    def test_bulk_costs_are_combined_and_materials_added(self):
        source = SCHEMA.edit(BASE, 'AllAttributeSaveData.AttributeParams[0].Value', 0)
        source = SCHEMA.edit(source, 'AlchemySaveData.TalentPoint', 0)
        result = progression.plan(source, 'alchemy')
        self.assertEqual([entry['id'] for entry in result['unlock_order']], [4000, 4011, 4017, 4080, 4082])
        state = progression.snapshot(apply_plan(source, result))
        self.assertEqual(state['gold'], 4050000)
        self.assertEqual(state['alchemy']['TalentPoint'], 13)
        self.assertEqual(state['owned'][10510], 10)
        self.assertEqual(state['owned'][10511], 4)
        self.assertEqual(result['new_items'], 1)

    def test_preparation_is_idempotent(self):
        result = progression.plan(BASE, 'alchemy')
        prepared = apply_plan(BASE, result)
        self.assertEqual(progression.plan(prepared, 'alchemy')['count'], 0)
        self.assertEqual(progression.plan(apply_plan(BASE, progression.plan(BASE, 'workshop', 20)), 'workshop', 20)['count'], 0)

    def test_unlock_rank_story_effects_and_unknown_bytes_remain_unchanged(self):
        source = BASE + encode_varint(900 << 3) + encode_varint(123456)
        prepared = apply_plan(source, progression.plan(source, 'alchemy'))
        before = SCHEMA.decode(source, 'SaveLoadSystem.GameSaveData')
        after = SCHEMA.decode(prepared, 'SaveLoadSystem.GameSaveData')
        before['AlchemySaveData'].pop('TalentPoint')
        after['AlchemySaveData'].pop('TalentPoint')
        self.assertEqual(before['AlchemySaveData'], after['AlchemySaveData'])
        for name in ('AllMapSaveData', 'AllMissionSaveData', 'StatisticSaveData', '@tag_900'):
            self.assertEqual(before[name], after[name])

    def test_dependency_order_is_topological(self):
        result = progression.plan(BASE, 'alchemy', talent_ids=[4082])
        self.assertEqual([entry['id'] for entry in result['unlock_order']], [4080, 4082])

    def test_story_nodes_cannot_be_prepared_as_unlocks(self):
        with self.assertRaisesRegex(ValueError, '故事节点'):
            progression.plan(BASE, 'alchemy', talent_ids=[4052])

    def test_story_unlock_flag_is_native_prerequisite(self):
        source = alter_document(BASE, lambda d: d['AlchemySaveData'].update(ActiveStoryTalentList=[]))
        result = progression.plan(source, 'alchemy', talent_ids=[4000])
        self.assertFalse(result['blockers'])

    def test_missing_story_is_reported_without_writing_story(self):
        source = alter_document(BASE, lambda d: d['AlchemySaveData'].update(UnlockTalentList=[], ActiveStoryTalentList=[]))
        result = progression.plan(source, 'alchemy', talent_ids=[4000])
        self.assertTrue(any('故事' in text for text in result['blockers']))
        self.assertFalse(any('Unlock' in change['path'] or 'Story' in change['path'] for change in result['changes']))

    def test_recipe_obtained_history_is_not_faked_by_inventory(self):
        source = alter_document(BASE, lambda d: d['StatisticSaveData'].update(ItemGetItemList=[], ItemGetCountList=[]))
        result = progression.plan(source, 'alchemy', talent_ids=[4017])
        self.assertTrue(any('实际获得原料' in text for text in result['blockers']))
        self.assertFalse(any(change['path'].startswith('Statistic') for change in result['changes']))
        self.assertNotIn(4017, [row['id'] for row in progression.plan(source, 'alchemy')['unlock_order']])

    def test_entry_quest_remains_game_driven(self):
        source = alter_document(BASE, lambda d: d['AllMissionSaveData'].update(FinishedMissionList=[]))
        result = progression.plan(source, 'alchemy', talent_ids=[4000])
        self.assertTrue(any('炼金入门' in text for text in result['blockers']))
        self.assertFalse(progression.overview(source)['alchemy']['entry_open'])
        self.assertEqual(progression.plan(source, 'alchemy')['count'], 0)

    def test_rank_blocker_preserves_current_rank(self):
        result = progression.plan(BASE, 'alchemy', talent_ids=[4001])
        self.assertTrue(any('Lv.16' in text for text in result['blockers']))
        self.assertEqual(progression.snapshot(apply_plan(BASE, result))['rank'], 12)

    def test_higher_resources_are_preserved(self):
        source = SCHEMA.edit(BASE, 'AlchemySaveData.TalentPoint', 999)
        result = progression.plan(source, 'alchemy')
        self.assertNotIn('AlchemySaveData.TalentPoint', [change['path'] for change in result['changes']])
        self.assertNotIn('AllAttributeSaveData.AttributeParams[0].Value', [change['path'] for change in result['changes']])

    def test_workshop_uses_current_rank_requirements(self):
        result = progression.plan(BASE, 'workshop', 13)
        modified = apply_plan(BASE, result)
        state = progression.snapshot(modified)
        self.assertEqual(state['stats']['IncomeMetrics'], 144000000)
        self.assertEqual(state['rank'], 12)
        self.assertGreaterEqual(state['favor'], 1400)
        self.assertEqual(state['stats']['BuildingMetrics'], 3000000)
        self.assertEqual(state['stats']['AsetheticMetrics'], 900000)
        self.assertTrue(any('美观' in text for text in result['blockers']))
        self.assertFalse(any('BuildingMetrics' in c['path'] or 'AsetheticMetrics' in c['path'] or 'FavorabilityMetrics' in c['path'] for c in result['changes']))

    def test_workshop_cap_and_no_downgrade(self):
        self.assertEqual(progression.plan(BASE, 'workshop', 10)['count'], 0)
        for bad in (0, 51, True, 12.5, '20'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                progression.plan(BASE, 'workshop', bad)

    def test_favor_respects_each_npc_maximum(self):
        data = apply_plan(BASE, progression.plan(BASE, 'workshop', 50))
        state = progression.snapshot(data)
        for row in state['npcs']:
            cap = max(progression.definitions()['npcs'][row['npcID']]['bnip'])
            self.assertLessEqual(row['favorValue'], cap)
        self.assertGreaterEqual(state['favor'], 8800)

    def test_unknown_duplicate_and_boolean_talents_rejected(self):
        for selection in ([999999], [4000, 4000], [True], [], '4000'):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                progression.plan(BASE, 'alchemy', talent_ids=selection)

    def test_invalid_material_groups_do_not_guess(self):
        config = copy.deepcopy(progression.definitions())
        config['groups'][11201]['bnpc'] = 2
        with patch.object(progression, 'definitions', return_value=config), self.assertRaises(ValueError):
            progression.plan(BASE, 'alchemy', talent_ids=[4011])

    def test_dependency_cycle_fails_closed(self):
        config = copy.deepcopy(progression.definitions())
        config['talents'][4080]['bnae'] = [4082]
        with patch.object(progression, 'definitions', return_value=config), self.assertRaisesRegex(ValueError, '循环'):
            progression.plan(BASE, 'alchemy', talent_ids=[4082])

    def test_existing_preset_composition_keeps_larger_supplies(self):
        result = presets.plan(BASE, [{'id':'super_inventory','value':9999}, {'id':'alchemy_ready'}, {'id':'workshop_ready','value':13}])
        iron = next(change for change in result['changes'] if change.get('item_id') == 10511)
        self.assertEqual(iron['value'], '9999')
        self.assertTrue(result['notes'])
        self.assertTrue(result['blockers'])

    def test_api_preview_reverses_and_exports_only_fixture(self):
        source_hash = hashlib.sha256(BASE).hexdigest()
        request = {'save':'SAVE_PIPER_0.bytes','sha256':source_hash,'kind':'workshop','target':13}
        plan = web_server.plan_progression(request)
        body = {'save':request['save'],'sha256':source_hash,'edits':plan['edits']}
        preview = web_server.edit_save(body)
        self.assertTrue(preview['original_preserved'])
        self.assertGreater(preview['count'], 0)
        exported = web_server.edit_save(body, export=True)
        self.assertTrue(exported['filename'])
        self.assertEqual((SAVE_DIR / 'SAVE_PIPER_0.bytes').read_bytes(), BASE)

    def test_stale_source_and_manual_unlock_writes_are_rejected(self):
        with self.assertRaisesRegex(ValueError, '存档已更新'):
            web_server.plan_progression({'save':'SAVE_PIPER_0.bytes','sha256':'wrong','kind':'alchemy'})
        for route in (progression.SHOP_PATH+'.CurrentRank', 'AlchemySaveData.UnlockTalentList[0]', 'AlchemySaveData.Level'):
            with self.subTest(route=route), self.assertRaises(ValueError):
                web_server.edit_save({'save':'SAVE_PIPER_0.bytes','sha256':hashlib.sha256(BASE).hexdigest(),
                                      'edits':[{'path':route,'value':'30'}]})


def tearDownModule():
    WORKSPACE.cleanup()


if __name__ == '__main__':
    unittest.main()
