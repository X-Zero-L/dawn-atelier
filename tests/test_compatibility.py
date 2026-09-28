"""Compatibility checks use synthetic binaries and bundled schema facts only."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import compatibility


class FakeLayout:
    def __init__(self, assembly, metadata):
        self.assembly, self.metadata = assembly, metadata
        self.type_count = 1

    def schema_contract(self):
        return {'SaveLoadSystem.Demo': {'shape': self.metadata.decode()}}

    def type_name(self, index):
        return 'SaveLoadSystem.Demo'

    def methods(self, index):
        return [{'name': 'Serialize', 'address': 4}]

    def offset(self, address, size):
        if address + size > len(self.assembly):
            raise ValueError('Short binary')
        return address


class CompatibilityChecks(unittest.TestCase):
    def profile(self):
        return {'id':'synthetic-build', 'schema':'thepiper-2026-09-25',
                'GameAssembly_sha256':compatibility.digest(b'HEADCODETAIL'),
                'global_metadata_sha256':compatibility.digest(b'fields'),
                'contract_sha256':compatibility.schema_contract_hash(FakeLayout(b'', b'fields')),
                'serializers':[{'type':'SaveLoadSystem.Demo','ordinal':0,'method':'Serialize',
                                'length':4,'sha256':compatibility.digest(b'CODE')}]}

    def fixture(self, folder, version='2099-01-01-hotfix'):
        root=Path(folder)
        (root/'ThePiper_Data/il2cpp_data/Metadata').mkdir(parents=True)
        (root/'GameAssembly.dll').write_bytes(b'HEADCODETAIL')
        (root/'ThePiper_Data/il2cpp_data/Metadata/global-metadata.dat').write_bytes(b'fields')
        manifests=root/'ThePiper_Data/StreamingAssets/yoo/Main'
        manifests.mkdir(parents=True)
        (manifests/'PackageManifest_Main.version').write_text(version,encoding='utf-8')
        if '/' not in version and '\\' not in version:
            (manifests/f'PackageManifest_Main_{version}.bytes').write_bytes(b'fixture manifest')
        return root

    def test_resource_date_is_not_an_exact_version_gate(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(compatibility,'profiles',return_value=[self.profile()]):
            game=self.fixture(folder)
            result=compatibility.inspect_game(game)
            self.assertEqual(result['mode'],'reviewed')
            self.assertEqual(result['package_version'],'2099-01-01-hotfix')

    def test_unrelated_binary_bytes_may_change(self):
        with patch.object(compatibility,'NativeLayout',FakeLayout):
            result=compatibility.match_structure(b'NEXTCODEDIFF',b'fields',[self.profile()])
        self.assertEqual(result['id'],'synthetic-build')

    def test_serialization_changes_are_not_accepted(self):
        with patch.object(compatibility,'NativeLayout',FakeLayout):
            self.assertIsNone(compatibility.match_structure(b'HEADC0DETAIL',b'fields',[self.profile()]))

    def test_metadata_contract_changes_are_not_accepted(self):
        with patch.object(compatibility,'NativeLayout',FakeLayout):
            self.assertIsNone(compatibility.match_structure(b'HEADCODETAIL',b'changed',[self.profile()]))

    def test_missing_probe_set_cannot_claim_structural_compatibility(self):
        profile=self.profile();profile.pop('serializers')
        with patch.object(compatibility,'NativeLayout',FakeLayout):
            self.assertIsNone(compatibility.match_structure(b'HEADCODETAIL',b'fields',[profile]))

    def test_unknown_build_uses_structural_result(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(compatibility,'profiles',return_value=[self.profile()]), patch.object(compatibility,'NativeLayout',FakeLayout):
            game=self.fixture(folder)
            (game/'GameAssembly.dll').write_bytes(b'NEXTCODETAIL')
            self.assertEqual(compatibility.inspect_game(game)['mode'],'structural')

    def test_unknown_changed_serializer_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(compatibility,'profiles',return_value=[self.profile()]), patch.object(compatibility,'NativeLayout',FakeLayout):
            game=self.fixture(folder)
            (game/'GameAssembly.dll').write_bytes(b'NEXTB4D!TAIL')
            with self.assertRaisesRegex(ValueError,'关键存档结构'):
                compatibility.inspect_game(game)

    def test_path_like_resource_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(compatibility,'profiles',return_value=[self.profile()]):
            game=self.fixture(folder,'../outside')
            with self.assertRaisesRegex(ValueError,'资源版本文件无效'):
                compatibility.inspect_game(game)

    def test_prepared_stamp_includes_asset_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            game=self.fixture(folder)
            before=compatibility.installation_stamp(game)
            manifest=game/'ThePiper_Data/StreamingAssets/yoo/Main/PackageManifest_Main_2099-01-01-hotfix.bytes'
            manifest.write_bytes(b'manifest changed independently of code')
            self.assertNotEqual(before,compatibility.installation_stamp(game))

    def test_latest_config_renames_are_canonicalized_by_tag(self):
        with tempfile.TemporaryDirectory() as folder:
            compatibility.install_schema({'schema':'thepiper-2026-09-28'},folder)
            actual=json.loads((Path(folder)/'schema/config_schema.json').read_text(encoding='utf-8'))
            favor=next(row for row in actual['types'] if row['name']=='Example.FavorNPCConfig')
            fields={row['protobuf_tag']:row for row in favor['fields']}
            self.assertEqual((fields[1]['name'],fields[1]['source_name']),('bnin','bnkp'))
            self.assertEqual((fields[2]['name'],fields[2]['source_name']),('bnio','bnkq'))
            self.assertEqual((fields[3]['name'],fields[3]['source_name']),('bnip','bnkr'))

    def test_latest_save_schema_keeps_new_crop_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            compatibility.install_schema({'schema':'thepiper-2026-09-28'},folder)
            actual=json.loads((Path(folder)/'schema/save_schema.json').read_text(encoding='utf-8'))
            crop=next(row for row in actual['types'] if row['name']=='SaveLoadSystem.FarmCropBuildingData')
            self.assertIn(('IsFirstHarvest',17),[(row['name'],row['protobuf_tag']) for row in crop['fields']])
            self.assertIn(('OriginalGeneList',18),[(row['name'],row['protobuf_tag']) for row in crop['fields']])

    def test_schema_directory_cannot_escape_bundle(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            compatibility.install_schema({'schema':'../outside'},folder)

    def test_installing_schema_does_not_mark_failed_preparation_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            report=Path(folder)/'compatibility.json'
            report.write_text('{"ready":true}',encoding='utf-8')
            compatibility.begin_preparation(folder)
            compatibility.install_schema({'schema':'thepiper-2026-09-28'},folder)
            self.assertFalse(report.exists())

    def test_incomplete_preparation_cannot_publish_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);game=self.fixture(root/'game');data=root/'data'
            compatibility.begin_preparation(data)
            compatibility.install_schema({'schema':'thepiper-2026-09-25'},data)
            with self.assertRaisesRegex(ValueError,'必要文件'):
                compatibility.complete_preparation({'installation_stamp':compatibility.installation_stamp(game)},data,game)
            self.assertFalse((data/'compatibility.json').exists())

    def test_running_service_rejects_a_new_preparation_snapshot(self):
        startup={'profile':'old','schema':'same','installation_stamp':[[1,2]],'manifest_sha256':'old'}
        current={**startup,'manifest_sha256':'updated'}
        with patch.object(compatibility,'require_prepared',return_value=current), self.assertRaisesRegex(ValueError,'运行期间'):
            compatibility.require_unchanged_install('game','data',startup)


if __name__=='__main__':
    unittest.main()
