"""The release worker is independent of edits and never starts subprocesses."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app_update import AppUpdates


class AppUpdateChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.updates = AppUpdates(self.home, '2.6.0', supported=True)

    def finish(self):
        self.updates.worker.join(2)
        self.assertFalse(self.updates.worker.is_alive())

    def test_source_mode_never_contacts_update_server(self):
        app = AppUpdates(self.home, '2.6.0', supported=False)
        with patch('app_update.latest_release') as fetch:
            self.assertEqual(app.check(True)['phase'], 'source')
        fetch.assert_not_called()

    def test_checking_current_release_is_throttled(self):
        with patch('app_update.latest_release', return_value=None) as fetch:
            self.updates.check()
            self.finish()
            self.updates.check()
            self.updates.check(True)
        fetch.assert_called_once_with('2.6.0')
        self.assertEqual(self.updates.status()['phase'], 'current')

    def test_preferences_survive_restart_and_manual_check_still_works(self):
        self.updates.set_automatic(False)
        restarted = AppUpdates(self.home, '2.6.0', supported=True)
        with patch('app_update.latest_release', return_value=None) as fetch:
            restarted.check()
            fetch.assert_not_called()
            restarted.check(True)
            restarted.worker.join(2)
        fetch.assert_called_once()
        self.assertFalse(restarted.status()['automatic'])

    def test_downloads_ready_package_without_installing(self):
        release = {'version': '2.7.0', 'archive': {}, 'manifest': {}}
        stage = {'version': '2.7.0', 'directory': str(self.home / 'updates/versions/test/DawnAtelier'), 'sha256': 'a' * 64}
        with patch('app_update.latest_release', return_value=release), patch('app_update.stage_release', return_value=stage) as download:
            self.updates.check()
            self.finish()
        self.assertEqual(download.call_args.args, (release, self.home / 'updates'))
        result = self.updates.status()
        self.assertEqual(result['phase'], 'ready')
        self.assertEqual(len(result['token']), 32)
        with self.assertRaises(ValueError):
            self.updates.take_stage('wrong')
        self.assertEqual(self.updates.take_stage(result['token']), stage)
        self.assertEqual(self.updates.status()['phase'], 'installing')

    def test_network_failure_stays_local_to_updater(self):
        with patch('app_update.latest_release', side_effect=OSError('offline')), self.assertLogs('app_update', level='ERROR'):
            self.updates.check()
            self.finish()
        self.assertEqual(self.updates.status()['phase'], 'error')
        self.assertIsNone(self.updates.stage)
        self.assertGreater(self.updates.next_check, 0)

    def test_downloaded_update_can_resume_without_network(self):
        self.updates.root.mkdir()
        release = {'version': '2.7.0', 'archive': {}, 'manifest': {}}
        (self.updates.root / 'pending.json').write_text(json.dumps(release), encoding='utf-8')
        with patch('app_update.latest_release') as fetch, patch('app_update.stage_release', return_value={'version': '2.7.0'}) as verify:
            self.updates.check()
            self.finish()
        fetch.assert_not_called()
        verify.assert_called_once()
        self.assertEqual(self.updates.status()['phase'], 'ready')

    def test_cancelled_download_never_becomes_ready(self):
        def cancelled(*args, **kwargs):
            self.updates.close()
            return {'version': '2.7.0'}
        with patch('app_update.latest_release', return_value={'version': '2.7.0'}), patch('app_update.stage_release', side_effect=cancelled):
            self.updates.check()
            self.finish()
        self.assertIsNone(self.updates.stage)
        self.assertNotEqual(self.updates.status()['phase'], 'ready')

    def test_failed_release_is_not_reinstalled_automatically(self):
        folder = self.home / 'updates'
        folder.mkdir()
        (folder / 'failed.json').write_text(json.dumps({'versions': ['2.7.0']}), encoding='utf-8')
        self.updates = AppUpdates(self.home, '2.6.0', supported=True)
        with patch('app_update.latest_release', return_value={'version': '2.7.0'}), patch('app_update.stage_release') as download:
            self.updates.check()
            self.finish()
        download.assert_not_called()
        self.assertEqual(self.updates.status()['phase'], 'error')


if __name__ == '__main__':
    unittest.main()
