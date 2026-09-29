"""Preparation failures must replace stale status and remain visible in logs."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import desktop_service


class DesktopPreparationChecks(unittest.TestCase):
    def test_compatibility_failure_is_logged_before_child_start(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            game = root / 'game'
            game.mkdir()
            (game / 'ThePiper.exe').write_bytes(b'fixture')
            failure = '检测到游戏版本 2099-02-03-update。关键存档结构或配置定义与已核对版本不同。'
            with patch.object(desktop_service, 'USER_ROOT', root), \
                 patch.object(desktop_service, 'LOG_ROOT', root / 'logs'), \
                 patch.object(desktop_service, 'read_config', return_value={}), \
                 patch.object(desktop_service, 'find_game', return_value=game), \
                 patch.object(desktop_service, 'inspect_game', side_effect=ValueError(failure)):
                service = desktop_service.DesktopService()
                data = service._data_root()
                data.mkdir(parents=True)
                for name in ('desktop-ready.json', 'compatibility.json'):
                    (data / name).write_text('{"ready":true}', encoding='utf-8')
                service._prepared = True
                with patch.object(service, '_popen') as child, self.assertRaisesRegex(ValueError, '2099-02-03-update'):
                    service._prepare()
                child.assert_not_called()
                self.assertFalse(service._prepared)
                self.assertFalse((data / 'desktop-ready.json').exists())
                self.assertFalse((data / 'compatibility.json').exists())
                self.assertIn(failure, (root / 'logs/prepare.log').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
