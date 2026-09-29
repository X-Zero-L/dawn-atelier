"""Background release checks and verified downloads for the Windows desktop."""

import json
import logging
import os
from pathlib import Path
import secrets
import threading
import time

from app_paths import FROZEN, USER_ROOT, app_version
from update_packages import latest_release, stage_release, parse_version


class AppUpdates:
    def __init__(self, home=None, version=None, supported=None):
        self.root = Path(home or USER_ROOT) / 'updates'
        self.version = version or app_version()
        self.supported = (FROZEN and os.name == 'nt') if supported is None else supported
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.worker = None
        self.next_check = 0
        self.last_check = None
        self.stage = None
        self.automatic = True
        try:
            self.automatic = json.loads((self.root / 'settings.json').read_text(encoding='utf-8')).get('automatic', True) is True
        except (OSError, ValueError, AttributeError):
            pass
        self.failed_versions = []
        self._state = {'phase': 'idle' if self.supported else 'source', 'version': self.version,
                       'percent': 0, 'token': '', 'message': '启动后自动检查新版' if self.supported else '源码版请通过 Git 更新'}
        try:
            result = json.loads((self.root / 'failed.json').read_text(encoding='utf-8'))
            if isinstance(result.get('versions'), list) and result['versions']:
                self.failed_versions = result['versions']
                self._state.update(message='上次更新未能启动，已恢复旧版。可手动检查更新后重试。')
        except (OSError, ValueError, AttributeError):
            pass

    def status(self):
        with self.lock:
            return {**self._state, 'supported': self.supported, 'automatic': self.automatic}

    def set_automatic(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('自动更新设置无效。')
        with self.lock:
            self.root.mkdir(parents=True, exist_ok=True)
            temporary = self.root / 'settings.json.tmp'
            temporary.write_text(json.dumps({'automatic': enabled}) + '\n', encoding='utf-8')
            temporary.replace(self.root / 'settings.json')
            self.automatic = enabled
            return self.status()

    def check(self, force=False):
        if type(force) is not bool:
            raise ValueError('更新检查参数无效。')
        with self.lock:
            now = time.monotonic()
            if (not self.supported or self.cancel.is_set() or self._state['phase'] == 'installing' or
                    self.worker and self.worker.is_alive() or self.stage and not force):
                return self.status()
            if not force and (not self.automatic or now < self.next_check):
                return self.status()
            if self.last_check is not None and now - self.last_check < 10:
                return self.status()
            self.last_check = now
            self.next_check = now + 6 * 3600
            self._state.update(phase='checking', message='正在检查工坊新版…', percent=0, token='')
            self.worker = threading.Thread(target=self._download, args=(force,), name='dawn-app-update', daemon=True)
            self.worker.start()
            return self.status()

    def _download(self, force):
        try:
            release = None
            # A fully downloaded update can finish after an offline restart.
            # stage_release rechecks the cached manifest and every payload file.
            pending = self.root / 'pending.json'
            if not force:
                try:
                    if pending.stat().st_size < 32768:
                        cached = json.loads(pending.read_text(encoding='utf-8'))
                        if parse_version(cached['version']) > parse_version(self.version):
                            release = cached
                except (OSError, ValueError, KeyError, TypeError):
                    pass
            if release is None:
                release = latest_release(self.version)
            if self.cancel.is_set():
                return
            if release is None:
                with self.lock:
                    self.stage = None
                    self._state.update(phase='current', version=self.version, message='已是最新版本', percent=0)
                return
            if release['version'] in self.failed_versions and not force:
                with self.lock:
                    self._state.update(phase='error', message='上次更新未能启动，已保留旧版。点击检查更新可重试。')
                return
            with self.lock:
                self._state.update(phase='downloading', version=release['version'], message='正在下载并校验新版…')
            def progress(percent, message):
                with self.lock:
                    self._state.update(percent=max(0, min(100, int(percent))), message=message)
            stage = stage_release(release, self.root, progress=progress, cancelled=self.cancel.is_set)
            if self.cancel.is_set():
                return
            with self.lock:
                self.root.mkdir(parents=True, exist_ok=True)
                temporary = self.root / 'pending.json.tmp'
                temporary.write_text(json.dumps({key: release[key] for key in ('version', 'archive', 'manifest')}) + '\n', encoding='utf-8')
                temporary.replace(pending)
                self.stage = stage
                self._state.update(phase='ready', version=stage['version'], percent=100,
                                   token=secrets.token_hex(16), message='新版已下载并校验，编辑空闲时自动重启更新。')
        except Exception:
            if self.cancel.is_set():
                return
            logging.getLogger(__name__).exception('Desktop update check or download failed')
            with self.lock:
                self.stage = None
                self.next_check = time.monotonic() + 30 * 60
                self._state.update(phase='error', token='', percent=0, message='更新检查或下载未完成。当前版本可继续使用，稍后会重试。')

    def take_stage(self, token):
        with self.lock:
            if self._state['phase'] != 'ready' or not self.stage or token != self._state['token'] or not token:
                raise ValueError('更新已变化，请重新检查。')
            self._state.update(phase='installing', message='正在保留旧版并准备重启…')
            return dict(self.stage)

    def install_failed(self, message):
        with self.lock:
            self._state.update(phase='error', token='', message=message)
            self.stage = None

    def close(self):
        self.cancel.set()
