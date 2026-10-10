"""Disposable fixtures prove the reusable framework without game resources."""

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from atelier import Editor, GameDescriptor, Registry, Snapshot, write_modified
from atelier.reference import JsonReferenceAdapter


class StatefulAdapter(JsonReferenceAdapter):
    descriptor = GameDescriptor('fixture-game', 'Fixture game', '1')

    def __init__(self):
        self.schema_revision = 1
        self.running = False
        self.validations = 0

    def compatibility(self, snapshot):
        return {'schema_revision': self.schema_revision}

    def validate(self, original, modified, operations):
        self.validations += 1
        super().validate(original, modified, operations)

    def runtime(self, snapshot, mode):
        if mode == 'apply' and self.running:
            raise RuntimeError('Fixture game is running')


class FrameworkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='atelier-framework-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'save.json'
        self.source.write_bytes(JsonReferenceAdapter.sample())
        self.original = self.source.read_bytes()
        self.operations = [{'action': 'set', 'target': '/player/gold', 'value': 999}]
        self.adapter = JsonReferenceAdapter()
        self.editor = Editor(self.adapter, self.root / 'backups')

    def plan(self, editor=None):
        return (editor or self.editor).preview(Snapshot.capture(self.source), self.operations)

    def test_snapshot_and_plan_are_immutable(self):
        snapshot = Snapshot.capture(self.source)
        with self.assertRaises(FrozenInstanceError):
            snapshot.data = b'changed'
        plan = self.plan()
        self.operations[0]['value'] = 0
        copy = plan.operations
        copy[0]['value'] = 1
        self.assertEqual(plan.operations[0]['value'], 999)
        self.assertFalse((self.root / 'backups').exists())

    def test_export_preserves_unknown_values_and_original_with_audit(self):
        plan = self.plan()
        result = self.editor.commit(plan, self.root / 'export.json', approval=plan.plan_id)
        self.assertEqual(self.source.read_bytes(), self.original)
        exported = json.loads((self.root / 'export.json').read_bytes())
        self.assertEqual(exported['player']['gold'], 999)
        self.assertEqual(exported['unknown'], {'preserved': True})
        self.assertEqual(Path(result['backup']).read_bytes(), self.original)
        self.assertEqual(Path(result['backup']).parent.name, 'json-reference')
        audit = json.loads(Path(result['audit']).read_text(encoding='utf-8'))
        self.assertEqual(audit['plan_id'], plan.plan_id)
        self.assertEqual(audit['adapter_id'], 'json-reference')
        self.assertEqual(audit['sha256_after'], result['sha256_after'])

    def test_changed_source_rejects_preview_and_commit(self):
        snapshot = Snapshot.capture(self.source)
        plan = self.plan()
        self.source.write_bytes(self.original + b' ')
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            self.editor.preview(snapshot, self.operations)
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            self.editor.commit(plan, self.root / 'output.json', approval=plan.plan_id)
        self.assertFalse((self.root / 'output.json').exists())

    def test_explicit_review_binding_rejects_tampering(self):
        plan = self.plan()
        review = plan.to_review()
        reopened = self.editor.review(review, plan.plan_id)
        self.assertEqual(reopened.modified, plan.modified)
        with self.assertRaisesRegex(ValueError, 'approval'):
            self.editor.review(review, 'wrong-id')
        review['operations'][0]['value'] = 888
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.editor.review(review, plan.plan_id)

    def test_forged_modified_bytes_are_rejected(self):
        plan = replace(self.plan(), modified=self.original)
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.editor.commit(plan, self.root / 'output.json', approval=plan.plan_id)

    def test_wrong_adapter_and_version_rejected(self):
        plan = self.plan()
        other = Editor(StatefulAdapter(), self.root / 'backups')
        with self.assertRaisesRegex(ValueError, 'different'):
            other.commit(plan, self.root / 'output.json', approval=plan.plan_id)
        other_plan = replace(plan, adapter_version='2')
        with self.assertRaisesRegex(ValueError, 'different'):
            self.editor.commit(other_plan, self.root / 'output.json', approval=other_plan.plan_id)

    def test_synthetic_and_read_only_cannot_apply(self):
        plan = self.plan()
        with self.assertRaisesRegex(PermissionError, 'Synthetic'):
            self.editor.commit(plan, self.source, approval=plan.plan_id, mode='apply')
        adapter = StatefulAdapter()
        adapter.descriptor = replace(adapter.descriptor, read_only=True)
        editor = Editor(adapter, self.root / 'backups')
        plan = self.plan(editor)
        with self.assertRaisesRegex(PermissionError, 'read-only'):
            editor.commit(plan, self.root / 'output.json', approval=plan.plan_id)

    def test_compatibility_and_runtime_rechecked_before_apply(self):
        adapter = StatefulAdapter()
        editor = Editor(adapter, self.root / 'backups')
        plan = self.plan(editor)
        adapter.schema_revision = 2
        with self.assertRaisesRegex(ValueError, 'compatibility changed'):
            editor.commit(plan, self.source, approval=plan.plan_id, mode='apply')
        plan = self.plan(editor)
        adapter.running = True
        with self.assertRaisesRegex(RuntimeError, 'running'):
            editor.commit(plan, self.source, approval=plan.plan_id, mode='apply')
        self.assertEqual(self.source.read_bytes(), self.original)
        adapter.running = False
        result = editor.commit(plan, self.source, approval=plan.plan_id, mode='apply')
        self.assertEqual(json.loads(self.source.read_bytes())['player']['gold'], 999)
        self.assertEqual(Path(result['backup']).read_bytes(), self.original)
        self.assertGreaterEqual(adapter.validations, 4)

    def test_mode_boundaries_and_approval(self):
        adapter = StatefulAdapter()
        editor = Editor(adapter, self.root / 'backups')
        plan = self.plan(editor)
        with self.assertRaisesRegex(ValueError, 'approval'):
            editor.commit(plan, self.source, approval='', mode='apply')
        with self.assertRaisesRegex(ValueError, 'Export'):
            editor.commit(plan, self.source, approval=plan.plan_id)
        with self.assertRaisesRegex(ValueError, 'Apply'):
            editor.commit(plan, self.root / 'other.json', approval=plan.plan_id, mode='apply')

    def test_registry_rejects_duplicates_and_unknown_ids(self):
        registry = Registry()
        registry.register(self.adapter)
        with self.assertRaisesRegex(ValueError, 'already registered'):
            registry.register(self.adapter)
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            registry.get('another-game')
        self.assertEqual(registry.descriptors()[0]['id'], 'json-reference')
        with self.assertRaises(ValueError):
            GameDescriptor('../unsafe', 'Unsafe', '1')

    def test_reference_rejects_invalid_operations_and_documents(self):
        for operations in (
            [], [{'action': 'set', 'target': '/absent', 'value': 1}],
            [{'action': 'set', 'target': '/player/gold', 'value': True}],
            [{'action': 'set', 'target': '/format', 'value': 'other'}],
            [{'action': 'set', 'target': '/player/gold', 'value': float('nan')}],
        ):
            with self.subTest(operations=operations), self.assertRaises(ValueError):
                self.editor.preview(Snapshot.capture(self.source), operations)
        for data in (b'{}', b'{"format":"atelier-reference-v1","x":1,"x":2}',
                     b'{"format":"atelier-reference-v1","x":NaN}'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.adapter.inspect(data)

    def test_transaction_legacy_name_and_callback(self):
        validations = []
        backup = write_modified(self.source, self.original, b'new bytes', self.root / 'out',
                                self.root / 'raw-backups', validate=lambda: validations.append(True))
        self.assertRegex(backup.name, r'^save\.json\.\d{8}-\d{6}-\d{6}\.bak$')
        self.assertEqual(backup.read_bytes(), self.original)
        self.assertEqual(len(validations), 2)

    def test_existing_destination_is_never_overwritten(self):
        target = self.root / 'output.json'
        target.write_bytes(b'keep this export')
        with self.assertRaises(FileExistsError):
            write_modified(self.source, self.original, b'new', target, self.root / 'backups')
        self.assertEqual(target.read_bytes(), b'keep this export')

    def test_concurrent_destination_creation_is_never_overwritten(self):
        target = self.root / 'output.json'
        calls = []

        def validate():
            calls.append(True)
            if len(calls) == 2:
                target.write_bytes(b'concurrent export')

        with self.assertRaises(FileExistsError):
            write_modified(self.source, self.original, b'new', target, self.root / 'backups', validate)
        self.assertEqual(target.read_bytes(), b'concurrent export')
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_concurrent_source_change_is_preserved(self):
        calls = []

        def validate():
            calls.append(True)
            if len(calls) == 2:
                self.source.write_bytes(b'game saved again')

        with self.assertRaisesRegex(RuntimeError, 'changed'):
            write_modified(self.source, self.original, b'new', self.source, self.root / 'backups', validate)
        self.assertEqual(self.source.read_bytes(), b'game saved again')
        self.assertFalse(list(self.root.glob('*.tmp')))
        self.assertEqual(next((self.root / 'backups').glob('*.bak')).read_bytes(), self.original)

    def test_unexpected_modified_reference_fields_rejected(self):
        modified = json.loads(self.adapter.transform(self.original, self.operations))
        modified['unknown']['preserved'] = False
        with self.assertRaisesRegex(ValueError, 'Unexpected'):
            self.adapter.validate(self.original, json.dumps(modified).encode(), self.operations)

    def test_compatibility_change_during_staging_rejects_publication(self):
        import atelier.transaction as transaction
        adapter = StatefulAdapter()
        editor = Editor(adapter, self.root / 'backups')
        plan = self.plan(editor)
        original_write = transaction._write_new

        def changing_write(path, data):
            original_write(path, data)
            if path.suffix == '.tmp':
                adapter.schema_revision += 1

        with patch('atelier.transaction._write_new', side_effect=changing_write):
            with self.assertRaisesRegex(ValueError, 'compatibility changed'):
                editor.commit(plan, self.source, approval=plan.plan_id, mode='apply')
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_audit_failure_reports_successful_edit_and_backup(self):
        plan = self.plan()
        with patch('atelier.editor.write_audit', side_effect=OSError('audit unavailable')):
            report = self.editor.commit(plan, self.root / 'output.json', approval=plan.plan_id)
        self.assertEqual(report['audit_error'], 'audit unavailable')
        self.assertEqual(Path(report['backup']).read_bytes(), self.original)
        self.assertEqual(Path(report['output']).read_bytes(), plan.modified)

    def test_compatibility_change_inside_final_transform_is_rejected(self):
        class ChangingAdapter(StatefulAdapter):
            calls = 0

            def transform(self, data, operations):
                self.calls += 1
                if self.calls == 3:
                    self.schema_revision += 1
                return super().transform(data, operations)

        adapter = ChangingAdapter()
        editor = Editor(adapter, self.root / 'backups')
        plan = self.plan(editor)
        with self.assertRaisesRegex(ValueError, 'compatibility changed'):
            editor.commit(plan, self.source, approval=plan.plan_id, mode='apply')
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_runtime_change_to_compatibility_rejects_publication(self):
        class ChangingAdapter(StatefulAdapter):
            def runtime(self, snapshot, mode):
                self.schema_revision += 1

        editor = Editor(ChangingAdapter(), self.root / 'backups')
        plan = self.plan(editor)
        with self.assertRaisesRegex(ValueError, 'compatibility changed'):
            editor.commit(plan, self.source, approval=plan.plan_id, mode='apply')
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_failed_partial_write_removes_only_its_new_file(self):
        from atelier.transaction import _write_new
        target = self.root / 'partial.tmp'
        with patch('atelier.transaction.os.fsync', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                _write_new(target, b'partially written')
        self.assertFalse(target.exists())
        target.write_bytes(b'owned by another process')
        with self.assertRaises(FileExistsError):
            _write_new(target, b'new')
        self.assertEqual(target.read_bytes(), b'owned by another process')

    def test_published_export_cleanup_error_keeps_success_and_audit(self):
        import os
        plan = self.plan()
        unlink = Path.unlink

        def link_publish(temporary, destination):
            os.link(temporary, destination)
            return True

        def locked_unlink(path, *args, **kwargs):
            if path.suffix == '.tmp':
                raise PermissionError('temporary locked')
            return unlink(path, *args, **kwargs)

        with patch('atelier.transaction._publish_export', side_effect=link_publish), patch.object(Path, 'unlink', locked_unlink):
            report = self.editor.commit(plan, self.root / 'output.json', approval=plan.plan_id)
        self.assertTrue(report['warnings'])
        self.assertTrue(Path(report['audit']).is_file())
        self.assertEqual(Path(report['output']).read_bytes(), plan.modified)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows publication strategy')
    def test_windows_export_does_not_need_hard_links(self):
        plan = self.plan()
        with patch('atelier.transaction.os.link', side_effect=OSError('hard links unsupported')):
            report = self.editor.commit(plan, self.root / 'output.json', approval=plan.plan_id)
        self.assertEqual(Path(report['output']).read_bytes(), plan.modified)


class FrameworkCLITests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-X', 'utf8', '-m', 'atelier', *map(str, args)],
                              cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
                              encoding='utf-8', timeout=30)

    def test_cli_review_export_and_template(self):
        with tempfile.TemporaryDirectory(prefix='atelier-cli-') as temporary:
            root = Path(temporary)
            source, operations, review = root / 'save.json', root / 'operations.json', root / 'review.json'
            result = self.run_cli('sample', source)
            self.assertEqual(result.returncode, 0, result.stderr)
            original = source.read_bytes()
            operations.write_text('[{"action":"set","target":"/player/gold","value":999}]')
            result = self.run_cli('inspect', '--game', 'json-reference', source)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.run_cli('preview', '--game', 'json-reference', source,
                                  '--operations', operations, '--review', review)
            self.assertEqual(result.returncode, 0, result.stderr)
            plan_id = json.loads(result.stdout)['plan_id']
            output = root / 'edited.json'
            result = self.run_cli('export', '--review', review, '--approve', 'wrong',
                                  '--backups', root / 'backups', '--output', output)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())
            result = self.run_cli('export', '--review', review, '--approve', plan_id,
                                  '--backups', root / 'backups', '--output', output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_bytes())['player']['gold'], 999)
            self.assertEqual(source.read_bytes(), original)
            result = self.run_cli('apply', '--review', review, '--approve', plan_id, '--backups', root / 'backups')
            self.assertNotEqual(result.returncode, 0)
            result = self.run_cli('scaffold', root / 'adapter', '--id', 'other-game', '--title', 'Other game')
            self.assertEqual(result.returncode, 0, result.stderr)
            template = (root / 'adapter' / 'adapter.py').read_text(encoding='utf-8')
            compile(template, 'adapter.py', 'exec')
            self.assertIn('read_only=True', template)
            result = self.run_cli('scaffold', root / 'adapter', '--id', 'other-game', '--title', 'Other game')
            self.assertNotEqual(result.returncode, 0)

    def test_registry_listing_imports_no_game_globals(self):
        result = subprocess.run([sys.executable, '-X', 'utf8', '-c',
                                 'import sys; from atelier.registry import builtins; builtins(); '
                                 'assert "app_config" not in sys.modules'],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
