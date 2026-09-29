"""Automatic game refresh uses temporary installations and never starts a child."""

from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, call, patch

import app_paths
import desktop_service


class GameUpdateChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.config_path = self.home / 'config.local.json'
        self.data = self.home / 'data/game'
        self.game = self.make_game('game')
        self.now = 100.0
        stack = ExitStack()
        self.addCleanup(stack.close)
        for owner, name, value in (
            (app_paths, 'USER_ROOT', self.home),
            (app_paths, 'CONFIG_PATH', self.config_path),
            (desktop_service, 'USER_ROOT', self.home),
            (desktop_service, 'LOG_ROOT', self.home / 'logs'),
        ):
            stack.enter_context(patch.object(owner, name, value))
        stack.enter_context(patch.object(desktop_service, 'find_game', return_value=self.game))
        stack.enter_context(patch.object(desktop_service, 'app_version', return_value='test'))
        stack.enter_context(patch.object(desktop_service, 'require_prepared', return_value={}))
        stack.enter_context(patch.object(desktop_service, 'profiles', return_value=[{'id': 'fixture'}]))
        stack.enter_context(patch.object(desktop_service.time, 'monotonic', side_effect=lambda: self.now))
        stack.enter_context(patch.object(desktop_service.DesktopService, '_popen',
                                        side_effect=AssertionError('Tests must not start a process.')))
        self.write_config({'game_dir': str(self.game)})

    def make_game(self, name):
        game = self.root / name
        metadata = game / 'ThePiper_Data/il2cpp_data/Metadata'
        manifest = game / 'ThePiper_Data/StreamingAssets/yoo/Main'
        metadata.mkdir(parents=True)
        manifest.mkdir(parents=True)
        (game / 'ThePiper.exe').write_bytes(b'fixture executable')
        (game / 'GameAssembly.dll').write_bytes(b'fixture assembly')
        (metadata / 'global-metadata.dat').write_bytes(b'fixture metadata')
        (manifest / 'PackageManifest_Main.version').write_text('test-build', encoding='utf-8')
        (manifest / 'PackageManifest_Main_test-build.bytes').write_bytes(b'fixture manifest')
        return game.resolve()

    def write_config(self, value):
        self.config_path.write_text(json.dumps(value), encoding='utf-8')

    def ready_install(self, game=None):
        game = game or self.game
        for name in ('configs/index.json', 'configs/物品目录.json', 'configs/分类目录.json',
                     'resources/summary.json', 'schema/save_schema.json',
                     'schema/config_schema.json', 'compatibility.json'):
            target = self.data / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('{}', encoding='utf-8')
        receipt = {'game_dir': str(game), 'files': desktop_service.installation_stamp(game),
                   'compatibility': {'profile': 'fixture'}}
        (self.data / 'desktop-ready.json').write_text(json.dumps(receipt), encoding='utf-8')
        return {'game_dir': receipt['game_dir'], 'files': receipt['files']}

    def service(self, prepared=True):
        if prepared:
            self.ready_install()
        return desktop_service.DesktopService()

    def change_install(self, contents=b'updated assembly with a different length'):
        (self.game / 'GameAssembly.dll').write_bytes(contents)

    def observe(self, service, at):
        self.now = at
        return service.check_game_update()['game_update']

    def candidate_ready(self, service, at=100):
        self.change_install()
        self.assertEqual(self.observe(service, at)['phase'], 'waiting')
        update = self.observe(service, at + 6)
        self.assertEqual(update['phase'], 'ready')
        return update['token']

    def finish_operation(self, service):
        self.assertIsNotNone(service._worker)
        service._worker.join(timeout=2)
        self.assertFalse(service._worker.is_alive(), 'Mocked refresh did not finish.')
        self.assertFalse(service.status()['busy'])

    def test_first_use_does_not_start_automatic_preparation(self):
        service = self.service(prepared=False)
        with patch.object(service, '_start') as start:
            self.assertEqual(self.observe(service, 100)['phase'], 'idle')
            self.change_install()
            self.assertEqual(self.observe(service, 110)['phase'], 'idle')
            self.assertEqual(self.observe(service, 120)['phase'], 'idle')
        start.assert_not_called()
        self.assertIsNone(service._update_baseline)

    def test_status_does_not_check_files_or_start_preparation(self):
        service = self.service()
        self.change_install()
        with patch.object(desktop_service, 'installation_stamp') as stamp, \
             patch.object(service, 'check_game_update') as check, patch.object(service, '_start') as start:
            state = service.status()
        self.assertEqual(state['game_update']['phase'], 'idle')
        self.assertTrue(state['prepared'])
        stamp.assert_not_called()
        check.assert_not_called()
        start.assert_not_called()

    def test_update_must_remain_stable_for_six_seconds(self):
        service = self.service()
        self.change_install()
        waiting = self.observe(service, 100)
        self.assertEqual(waiting['phase'], 'waiting')
        self.assertFalse(service.status()['prepared'])
        self.assertEqual(self.observe(service, 105)['phase'], 'waiting')
        ready = self.observe(service, 106)
        self.assertEqual(ready['phase'], 'ready')
        self.assertEqual(ready['token'], waiting['token'])
        self.assertIsNone(service._worker)

    def test_changed_candidate_restarts_quiet_period_and_replaces_token(self):
        service = self.service()
        self.change_install()
        first = self.observe(service, 100)
        self.change_install(b'another update')
        second = self.observe(service, 103)
        self.assertNotEqual(first['token'], second['token'])
        self.assertEqual(self.observe(service, 108)['phase'], 'waiting')
        self.assertEqual(self.observe(service, 109)['phase'], 'ready')

    def test_temporarily_missing_files_restart_quiet_period(self):
        service = self.service()
        self.change_install()
        first = self.observe(service, 100)
        metadata = self.game / 'ThePiper_Data/il2cpp_data/Metadata/global-metadata.dat'
        original = metadata.read_bytes()
        metadata.unlink()
        missing = self.observe(service, 103)
        self.assertEqual(missing['phase'], 'waiting')
        self.assertEqual(missing['token'], '')
        self.assertIsNone(service._update_candidate)
        metadata.write_bytes(original)
        restored = self.observe(service, 104)
        self.assertNotEqual(restored['token'], first['token'])
        self.assertEqual(self.observe(service, 109)['phase'], 'waiting')
        self.assertEqual(self.observe(service, 110)['phase'], 'ready')

    def test_expired_or_empty_token_cannot_start_refresh(self):
        service = self.service()
        old_token = self.candidate_ready(service)
        self.change_install(b'another candidate')
        self.observe(service, 107)
        latest = self.observe(service, 113)
        self.assertNotEqual(old_token, latest['token'])
        with patch.object(service, '_start') as start:
            for token in (old_token, '', 'not-the-current-token'):
                with self.subTest(token=token):
                    self.assertEqual(service.refresh_game_update(token)['game_update']['phase'], 'ready')
        start.assert_not_called()

    def test_files_changed_after_idle_acknowledgment_are_rechecked(self):
        service = self.service()
        token = self.candidate_ready(service)
        self.change_install(b'replaced just before refresh')
        with patch.object(service, '_start') as start:
            update = service.refresh_game_update(token)['game_update']
        self.assertEqual(update['phase'], 'waiting')
        self.assertNotEqual(update['token'], token)
        start.assert_not_called()

    def test_demo_session_is_not_stopped_or_replaced(self):
        service = self.service()
        service._mode = 'demo'
        service._active_url = 'http://127.0.0.1:18767'
        service._workbench_session = 'demo-session'
        token = self.candidate_ready(service)
        with patch.object(service, '_start') as start, patch.object(service, '_stop_service') as stop:
            state = service.refresh_game_update(token)
        self.assertEqual(state['mode'], 'demo')
        self.assertEqual(state['active_url'], 'http://127.0.0.1:18767')
        self.assertEqual(state['workbench_session'], 'demo-session')
        start.assert_not_called()
        stop.assert_not_called()

    def test_external_browser_is_not_stopped_automatically(self):
        service = self.service()
        service._mode = 'game'
        service._active_url = 'http://127.0.0.1:18766'
        with patch.object(desktop_service.webbrowser, 'open'):
            service.open_browser()
        token = self.candidate_ready(service)
        with patch.object(service, '_start') as start:
            state = service.refresh_game_update(token)
        self.assertTrue(state['external_workbench'])
        self.assertEqual(state['active_url'], 'http://127.0.0.1:18766')
        start.assert_not_called()

    def test_failed_stamp_is_not_retried_by_subsequent_polls(self):
        service = self.service()
        token = self.candidate_ready(service)
        with patch.object(service, '_prepare', side_effect=ValueError('fixture failure')) as prepare, \
             patch.object(service, '_launch') as launch:
            service.refresh_game_update(token)
            self.finish_operation(service)
            for at in (107, 112, 130):
                self.assertEqual(self.observe(service, at)['phase'], 'failed')
                service.refresh_game_update(token)
        prepare.assert_called_once_with()
        launch.assert_not_called()
        self.assertEqual(service.status()['error'], 'fixture failure')

    def test_a_later_installation_can_be_tried_after_failure(self):
        service = self.service()
        token = self.candidate_ready(service)
        with patch.object(service, '_prepare', side_effect=ValueError('fixture failure')) as prepare, \
             patch.object(service, '_launch') as launch:
            service.refresh_game_update(token)
            self.finish_operation(service)
            self.change_install(b'next game update')
            self.assertEqual(self.observe(service, 110)['phase'], 'waiting')
            latest = self.observe(service, 116)
            self.assertEqual(latest['phase'], 'ready')
            service.refresh_game_update(latest['token'])
            self.finish_operation(service)
        self.assertEqual(prepare.call_count, 2)
        launch.assert_not_called()

    def test_manual_retry_remains_available_after_automatic_failure(self):
        service = self.service()
        token = self.candidate_ready(service)
        with patch.object(service, '_prepare', side_effect=ValueError('fixture failure')) as prepare:
            service.refresh_game_update(token)
            self.finish_operation(service)
            self.assertEqual(service.status()['game_update']['phase'], 'failed')
            service.prepare()
            self.finish_operation(service)
        self.assertEqual(prepare.call_count, 2)
        self.assertFalse(service.status()['auto_prepare'])

    def test_reselecting_same_path_does_not_repeat_automatic_attempt(self):
        service = self.service()
        token = self.candidate_ready(service)
        with patch.object(service, '_prepare', side_effect=ValueError('fixture failure')) as prepare:
            service.refresh_game_update(token)
            self.finish_operation(service)
            service.set_game(str(self.game))
            self.assertNotEqual(self.observe(service, 120)['phase'], 'ready')
            self.assertNotEqual(self.observe(service, 126)['phase'], 'ready')
        prepare.assert_called_once_with()

    def test_selecting_same_directory_keeps_baseline_and_other_directory_is_isolated(self):
        service = self.service()
        baseline = service._update_baseline
        service.set_game(str(self.game))
        self.assertEqual(service._update_baseline, baseline)
        other_game = self.make_game('other-game')
        service.set_game(str(other_game))
        self.assertIsNone(service._update_baseline)
        self.assertEqual(self.observe(service, 120)['phase'], 'idle')
        service.set_game(str(self.game))
        self.assertEqual(service._update_baseline, baseline)

    def test_success_runs_preparation_before_launching_game(self):
        service = self.service()
        token = self.candidate_ready(service)
        operations = Mock()
        with patch.object(service, '_prepare', operations.prepare), \
             patch.object(service, '_launch', operations.launch):
            service.refresh_game_update(token)
            self.finish_operation(service)
        self.assertEqual(operations.mock_calls, [call.prepare(), call.launch('game')])
        self.assertEqual(service.status()['error'], '')
        self.assertFalse(service.status()['auto_prepare'])

    def test_config_keeps_baseline_when_failed_preparation_removes_markers(self):
        service = self.service()
        baseline = service._update_baseline
        token = self.candidate_ready(service)
        with patch.object(desktop_service, 'inspect_game', side_effect=ValueError('unsupported fixture')), \
             patch.object(service, '_launch') as launch:
            service.refresh_game_update(token)
            self.finish_operation(service)
        launch.assert_not_called()
        self.assertFalse((self.data / 'desktop-ready.json').exists())
        self.assertFalse((self.data / 'compatibility.json').exists())
        config = json.loads(self.config_path.read_text(encoding='utf-8'))
        self.assertEqual(config['last_prepared_install'], baseline)
        restarted = desktop_service.DesktopService()
        self.assertEqual(restarted._update_baseline, baseline)
        self.change_install(b'next install after restarting the app')
        self.assertEqual(self.observe(restarted, 120)['phase'], 'waiting')
        self.assertEqual(self.observe(restarted, 126)['phase'], 'ready')


if __name__ == '__main__':
    unittest.main()
