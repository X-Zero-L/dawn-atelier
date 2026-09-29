"""Update handoff checks use temporary packages and never start a process."""

from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import updates_install as updates


class UpdateHandoffChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.original = self.package(self.root / 'user-program', '2.6.0')
        (self.original / 'personal.save').write_bytes(b'never copy or modify')
        (self.home / 'config.local.json').write_bytes(b'user settings')
        (self.home / 'draft.json').write_bytes(b'user draft')
        self.new = self.package(self.home / 'updates/releases/2.7.0/DawnAtelier', '2.7.0')
        self.stage = {'directory': str(self.new), 'version': '2.7.0', 'sha256': 'a' * 64}
        self.parent = Mock(created=12345)
        self.parent.wait.return_value = True
        self.child = Mock(pid=4567)
        self.child.poll.return_value = None
        self.child.wait.return_value = 0
        self.clock = 10.0
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(updates, '_Parent', return_value=self.parent))
        stack.enter_context(patch.object(updates.time, 'monotonic', side_effect=lambda: self.clock))
        stack.enter_context(patch.object(updates.time, 'sleep', side_effect=self.advance))
        stack.enter_context(patch.object(updates, 'START_TIMEOUT', 0.5))
        self.launch = stack.enter_context(patch.object(updates, '_launch', return_value=self.child))
        stack.enter_context(patch.object(updates.subprocess, 'Popen', side_effect=AssertionError('No real processes.')))
        self.original_bytes = self.snapshot(self.original)
        self.user_bytes = {name: (self.home / name).read_bytes() for name in ('config.local.json', 'draft.json')}

    def package(self, directory, version):
        directory.mkdir(parents=True)
        executable = bytearray(256)
        executable[:2] = b'MZ'
        struct.pack_into('<I', executable, 0x3C, 128)
        executable[128:132] = b'PE\0\0'
        struct.pack_into('<H', executable, 132, 0x8664)
        struct.pack_into('<H', executable, 152, 0x20B)
        struct.pack_into('<H', executable, 220, 2)
        contents = {'DawnAtelier.exe': bytes(executable),
                    '_internal/version.json': json.dumps({'version': version}).encode(),
                    '_internal/desktop/index.html': b'<p>fixture</p>'}
        rows = []
        for name, data in contents.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            rows.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        manifest = {'format': 'dawn-atelier-windows-package-v1', 'version': version, 'files': rows,
                    'platform': 'windows-x64', 'architecture': 'AMD64', 'entryPoint': 'DawnAtelier.exe'}
        (directory / 'package-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        return directory

    @staticmethod
    def verify(directory, expected_version):
        return updates.verify_installation(directory, expected_version)

    @staticmethod
    def snapshot(directory):
        return {path.relative_to(directory).as_posix(): path.read_bytes() for path in directory.rglob('*') if path.is_file()}

    @staticmethod
    def read(path):
        return json.loads(path.read_text(encoding='utf-8'))

    def advance(self, seconds):
        self.clock += seconds

    def prepare(self, **options):
        self.job = updates.prepare_handoff(self.stage, self.home, self.original / 'DawnAtelier.exe', **options)
        self.payload = self.read(self.job)
        return self.job

    def receipt(self, nonce=None):
        updates._write(self.job.with_suffix('.ready'), {
            'nonce': nonce if nonce is not None else self.payload['nonce'], 'version': self.stage['version'],
            'directory': str(self.new), 'pid': self.child.pid}, self.home)

    def assert_protected(self):
        self.assertEqual(self.snapshot(self.original), self.original_bytes)
        self.assertEqual({name: (self.home / name).read_bytes() for name in self.user_bytes}, self.user_bytes)

    def activate(self):
        updates._write(self.home / 'updates/active.json', {
            'format': 'dawn-atelier-active-v1', 'successful': True,
            'version': self.stage['version'], 'directory': str(self.new)}, self.home)

    def test_prepare_makes_verified_independent_copy_of_manifest_files(self):
        job = self.prepare(mode='game', browser=True)
        previous = Path(self.payload['previous'])
        self.assertEqual(len(job.stem), 32)
        self.assertEqual(job.parent, self.home / 'updates/jobs')
        self.assertEqual(self.payload['parent_pid'], os.getpid())
        self.assertEqual(self.payload['parent_created'], 12345)
        self.assertEqual(self.payload['mode'], 'game')
        self.assertTrue(self.payload['browser'])
        self.verify(previous, '2.6.0')
        self.assertFalse((previous / 'personal.save').exists())
        self.assertEqual(set(self.snapshot(previous)), set(self.original_bytes) - {'personal.save'})
        self.assert_protected()

    def test_copy_does_not_follow_unlisted_personal_directories(self):
        (self.original / 'saves').mkdir()
        (self.original / 'saves/slot1.json').write_text('private', encoding='utf-8')
        self.prepare()
        self.assertFalse((Path(self.payload['previous']) / 'saves').exists())

    def test_stage_outside_updates_and_traversal_are_rejected(self):
        for value in (str(self.original), str(self.home / 'updates/releases/../escape')):
            with self.subTest(path=value), self.assertRaises(ValueError):
                updates.prepare_handoff({**self.stage, 'directory': value}, self.home,
                                        self.original / 'DawnAtelier.exe')
        self.assert_protected()

    def test_ancestor_reparse_point_is_rejected_before_copy(self):
        existing = Path.lstat
        def lstat(path):
            if path == self.home / 'updates':
                return types.SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            return existing(path)
        with patch.object(Path, 'lstat', lstat), self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse((self.home / 'updates/rollback').exists())

    def test_parent_ready_precedes_wait_and_launch(self):
        self.prepare()
        def parent_wait(timeout):
            self.assertEqual(timeout, 60)
            self.assertEqual(self.read(self.job.with_suffix('.helper-ready'))['nonce'], self.payload['nonce'])
            self.launch.assert_not_called()
            return True
        self.parent.wait.side_effect = parent_wait
        def launch(*_):
            self.receipt()
            return self.child
        self.launch.side_effect = launch
        self.assertTrue(updates.run_handoff(self.job, self.home))
        active = self.read(self.home / 'updates/active.json')
        self.assertTrue(active['successful'])
        self.assertEqual(active['directory'], str(self.new))
        self.assertEqual(active['previous'], self.payload['previous'])
        self.child.terminate.assert_not_called()
        self.assert_protected()

    def test_new_process_receives_ticket_mode_and_same_home(self):
        self.prepare(mode='game', browser=True)
        def launch(*_):
            self.receipt()
            return self.child
        self.launch.side_effect = launch
        self.assertTrue(updates.run_handoff(self.job, self.home))
        self.launch.assert_called_once_with(self.new / 'DawnAtelier.exe', self.home,
            ['--update-ticket', str(self.job), '--resume', 'game', '--browser'])

    def test_successful_manual_retry_unskips_the_working_version(self):
        self.prepare()
        updates._mark_failed(self.home, '2.7.0')
        def launch(*_):
            self.receipt()
            return self.child
        self.launch.side_effect = launch
        self.assertTrue(updates.run_handoff(self.job, self.home))
        self.assertEqual(self.read(self.home / 'updates/failed.json')['versions'], [])

    def test_wrong_nonce_rolls_back_only_owned_child_and_skips_version(self):
        self.prepare(mode='demo')
        def launch(*_):
            self.receipt('b' * 64)
            return self.child
        self.launch.side_effect = launch
        self.assertFalse(updates.run_handoff(self.job, self.home))
        self.child.terminate.assert_called_once_with()
        self.child.wait.assert_called_once_with(timeout=5)
        self.assertEqual(self.launch.call_args.args, (Path(self.payload['previous']) / 'DawnAtelier.exe',
                         self.home, ['--skip-app-update', '--resume', 'demo']))
        self.assertEqual(self.read(self.home / 'updates/failed.json')['versions'], ['2.7.0'])
        self.assertTrue(self.read(self.home / 'updates/notice.json')['rollback'])
        self.assertFalse((self.home / 'updates/active.json').exists())
        self.assert_protected()

    def test_timeout_is_bounded_and_keeps_last_successful_active(self):
        self.prepare()
        self.activate()
        before = (self.home / 'updates/active.json').read_bytes()
        self.assertFalse(updates.run_handoff(self.job, self.home))
        self.assertLessEqual(self.clock, 10.5)
        self.assertEqual(self.launch.call_count, 2)
        self.assertEqual((self.home / 'updates/active.json').read_bytes(), before)
        self.assert_protected()

    def test_immediate_new_exit_rolls_back_without_terminating_exited_process(self):
        self.prepare()
        self.child.poll.return_value = 17
        self.assertFalse(updates.run_handoff(self.job, self.home))
        self.child.terminate.assert_not_called()
        self.assertEqual(self.launch.call_count, 2)

    def test_unresponsive_owned_child_uses_bounded_kill_before_rollback(self):
        self.prepare()
        self.child.wait.side_effect = [subprocess.TimeoutExpired('fixture', 5), 0]
        self.assertFalse(updates.run_handoff(self.job, self.home))
        self.child.terminate.assert_called_once_with()
        self.child.kill.assert_called_once_with()
        self.assertEqual(self.child.wait.call_count, 2)
        self.assertEqual(self.launch.call_count, 2)
        self.assert_protected()

    def test_corrupted_rollback_after_launch_is_not_executed(self):
        self.prepare()
        def launch(*_):
            (Path(self.payload['previous']) / 'DawnAtelier.exe').write_bytes(b'corrupted')
            return self.child
        self.launch.side_effect = launch
        self.assertFalse(updates.run_handoff(self.job, self.home))
        self.launch.assert_called_once()
        self.assertFalse(self.read(self.home / 'updates/notice.json')['rollback'])
        self.assert_protected()

    def test_status_write_failure_does_not_prevent_rollback(self):
        self.prepare()
        with patch.object(updates, '_mark_failed', side_effect=OSError('fixture read-only status')):
            self.assertFalse(updates.run_handoff(self.job, self.home))
        self.assertEqual(self.launch.call_count, 2)
        self.child.terminate.assert_called_once_with()
        self.assert_protected()

    def test_corrupted_current_distribution_does_not_create_a_job(self):
        (self.original / '_internal/version.json').write_bytes(b'corrupted')
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse((self.home / 'updates/jobs').exists())
        self.launch.assert_not_called()

    def test_parent_still_running_aborts_without_launching_either_version(self):
        self.prepare()
        self.parent.wait.return_value = False
        self.assertFalse(updates.run_handoff(self.job, self.home))
        self.launch.assert_not_called()
        self.assertFalse((self.home / 'updates/failed.json').exists())
        self.assert_protected()

    def test_cancelled_handoff_does_not_restart_after_parent_later_exits(self):
        self.prepare()
        self.job.with_suffix('.cancelled').write_text('cancelled\n', encoding='utf-8')
        self.assertFalse(updates.run_handoff(self.job, self.home))
        self.launch.assert_not_called()
        self.assertFalse((self.home / 'updates/failed.json').exists())
        self.assert_protected()

    def test_one_job_cannot_be_replayed(self):
        self.prepare()
        self.parent.wait.return_value = False
        self.assertFalse(updates.run_handoff(self.job, self.home))
        with self.assertRaises(FileExistsError):
            updates.run_handoff(self.job, self.home)
        self.launch.assert_not_called()

    def test_job_path_and_previous_path_cannot_escape_update_storage(self):
        self.prepare()
        with self.assertRaises(ValueError):
            updates.run_handoff(self.home / self.job.name, self.home)
        self.payload['previous'] = str(self.original)
        self.job.write_text(json.dumps(self.payload), encoding='utf-8')
        with self.assertRaises(ValueError):
            updates.run_handoff(self.job, self.home)
        self.launch.assert_not_called()
        self.assert_protected()

    def test_acknowledgement_requires_exact_target_version_and_helper_nonce(self):
        self.prepare()
        updates._write(self.job.with_suffix('.helper-ready'), {'nonce': self.payload['nonce']}, self.home)
        for executable, version in ((self.original / 'DawnAtelier.exe', '2.7.0'),
                                    (self.new / 'DawnAtelier.exe', '2.6.0')):
            with self.subTest(executable=executable, version=version), self.assertRaises(ValueError):
                updates.acknowledge_start(self.job, self.home, executable, version)
        updates._write(self.job.with_suffix('.helper-ready'), {'nonce': 'wrong'}, self.home)
        with self.assertRaises(ValueError):
            updates.acknowledge_start(self.job, self.home, self.new / 'DawnAtelier.exe', '2.7.0')
        self.assertFalse(self.job.with_suffix('.ready').exists())

    def test_acknowledgement_writes_authenticated_receipt(self):
        self.prepare()
        updates._write(self.job.with_suffix('.helper-ready'), {'nonce': self.payload['nonce']}, self.home)
        updates.acknowledge_start(self.job, self.home, self.new / 'DawnAtelier.exe', '2.7.0')
        receipt = self.read(self.job.with_suffix('.ready'))
        self.assertEqual(receipt, {'nonce': self.payload['nonce'], 'version': '2.7.0',
                                 'directory': str(self.new), 'pid': os.getpid()})

    def test_launcher_redirects_only_allowed_arguments_to_newer_verified_target(self):
        self.activate()
        result = updates.redirect_to_active(self.home, self.original / 'DawnAtelier.exe',
            ['--home', 'untrusted', '--resume', 'demo', '--browser', '--unknown', 'ignored'])
        self.assertTrue(result)
        self.launch.assert_called_once_with(self.new / 'DawnAtelier.exe', self.home,
                                            ['--resume', 'demo', '--browser'])
        self.assert_protected()

    def test_redirect_is_skipped_for_tickets_rollback_and_current_target(self):
        self.activate()
        for arguments in (['--update-ticket', 'job'], ['--update-ticket=job'],
                          ['--skip-app-update'], ['--internal-task', 'update']):
            self.assertFalse(updates.redirect_to_active(self.home, self.original / 'DawnAtelier.exe', arguments))
        self.assertFalse(updates.redirect_to_active(self.home, self.new / 'DawnAtelier.exe', []))
        self.launch.assert_not_called()

    def test_equal_or_older_cached_version_is_not_launched(self):
        self.activate()
        active = self.read(self.home / 'updates/active.json')
        for version in ('2.6.0', '2.5.0'):
            updates._write(self.home / 'updates/active.json', {**active, 'version': version}, self.home)
            self.assertFalse(updates.redirect_to_active(self.home, self.original / 'DawnAtelier.exe', []))
        self.launch.assert_not_called()

    def test_corrupt_active_package_falls_back_with_notice(self):
        self.activate()
        (self.new / 'DawnAtelier.exe').write_bytes(b'corrupted')
        self.assertFalse(updates.redirect_to_active(self.home, self.original / 'DawnAtelier.exe', []))
        self.launch.assert_not_called()
        self.assertIn('当前版本', self.read(self.home / 'updates/notice.json')['message'])
        self.assert_protected()

    def test_failed_version_is_not_redirected_on_later_launch(self):
        self.activate()
        updates._mark_failed(self.home, '2.7.0')
        self.assertFalse(updates.redirect_to_active(self.home, self.original / 'DawnAtelier.exe', []))
        self.launch.assert_not_called()

    def test_malformed_active_record_cannot_launch_or_escape(self):
        self.activate()
        path = self.home / 'updates/active.json'
        active = self.read(path)
        for payload in ({**active, 'directory': str(self.original)}, {**active, 'successful': False}, {}):
            updates._write(path, payload, self.home)
            self.assertFalse(updates.redirect_to_active(self.home, self.original / 'DawnAtelier.exe', []))
        self.launch.assert_not_called()
        self.assert_protected()


class UpdateLaunchEnvironmentChecks(unittest.TestCase):
    def test_launch_uses_argument_list_and_clears_inherited_workspaces(self):
        # _launch itself is isolated here so no executable is actually opened.
        with patch.dict(os.environ, {name: 'fixture' for name in updates._CLEAR_ENV}), \
             patch.object(updates.subprocess, 'Popen') as popen:
            executable = Path('C:/Program Files/Dawn Atelier/DawnAtelier.exe')
            home = Path('C:/Users/Test/AppData/Local/DawnAtelier')
            updates._launch(executable, home, ['--resume', 'game'])
        arguments, options = popen.call_args
        self.assertEqual(arguments[0], [str(executable), '--home', str(home), '--resume', 'game'])
        self.assertEqual(options['cwd'], str(executable.parent))
        self.assertFalse(updates._CLEAR_ENV & set(options['env']))
        self.assertEqual(options['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')
        self.assertNotIn('shell', options)


if __name__ == '__main__':
    unittest.main()
