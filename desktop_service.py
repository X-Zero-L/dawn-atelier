"""Desktop lifecycle: prepare local resources and own one workbench process."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
from urllib.request import build_opener, ProxyHandler, Request
from urllib.parse import urlparse
import webbrowser

from app_paths import APP_ROOT, USER_ROOT, LOG_ROOT, app_version, read_config, write_config, task_command, find_game
from compatibility import inspect_game, installation_stamp, profiles, require_prepared, begin_preparation


class DesktopService:
    def __init__(self):
        USER_ROOT.mkdir(parents=True, exist_ok=True)
        LOG_ROOT.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._worker = None
        self._child = None
        self._prepare_process = None
        self._closing = False
        self._window = None
        self._error = ''
        self._busy = False
        self._mode = None
        self._active_url = None
        self._ready_file = None
        self._workbench_session = None
        self._external_workbench = False
        self._attempted_updates = set()
        self._auto_prepare_active = False
        self._progress = {'percent': 0, 'stage': 'idle', 'message': '选择游戏，开始准备', 'detail': ''}
        self._config = read_config()
        self._game_dir = self._detect_game()
        self._prepared = self._is_prepared()
        self._reset_update_watch()
        if self._prepared:
            self._progress.update(percent=100, stage='ready', message='工坊准备就绪')

    def _detect_game(self):
        saved = self._config.get('game_dir')
        found = Path(saved).expanduser() if saved else find_game(self._config)
        return str(found.resolve()) if (found / 'ThePiper.exe').is_file() else ''

    def _path(self, name, fallback):
        path = Path(self._config.get(name) or fallback).expanduser()
        return path.resolve() if path.is_absolute() else (USER_ROOT / path).resolve()

    def _data_root(self, mode='game'):
        return USER_ROOT / 'data/demo' if mode == 'demo' else self._path('data_dir', 'data/game')

    def _is_prepared(self):
        if not self._game_dir:
            return False
        root = self._data_root()
        try:
            require_prepared(self._game_dir, root)
            receipt = json.loads((root / 'desktop-ready.json').read_text(encoding='utf-8'))
            game = Path(self._game_dir)
            return (receipt['game_dir'] == str(game.resolve()) and
                    receipt.get('compatibility', {}).get('profile') in {profile['id'] for profile in profiles()} and
                    receipt['files'] == installation_stamp(game) and
                    all((root / relative).is_file() for relative in
                        ('configs/index.json', 'configs/物品目录.json', 'configs/分类目录.json', 'resources/summary.json',
                         'schema/save_schema.json', 'schema/config_schema.json', 'compatibility.json')))
        except (OSError, ValueError, KeyError):
            return False

    def _state(self):
        if self._child and self._child.poll() is not None and self._active_url:
            self._active_url = None
            self._mode = None
            self._error = '工作台已停止，可以重新打开；排查详情见日志文件夹。'
        compatibility = None
        try:
            compatibility = json.loads((self._data_root() / 'compatibility.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        return {'version': app_version(), 'game_dir': self._game_dir, 'detected': bool(self._game_dir),
                'prepared': self._prepared, 'data_dir': str(USER_ROOT), 'busy': self._busy,
                'auto_prepare': self._auto_prepare_active,
                'game_update': dict(self._game_update), 'workbench_session': self._workbench_session,
                'external_workbench': self._external_workbench,
                'progress': dict(self._progress), 'error': self._error, 'mode': self._mode,
                'active_url': self._active_url, 'last_prepared': self._config.get('last_prepared'),
                'compatibility': compatibility}

    def status(self):
        with self._lock:
            return self._state()

    def _reset_update_watch(self):
        self._update_baseline = None
        self._update_candidate = None
        self._update_seen_at = 0
        self._update_checked_at = None
        self._game_update = {'phase': 'idle', 'message': '', 'token': ''}
        # A failed preparation removes readiness. Keep the previous successful
        # identity separately so a later game update can still be detected.
        previous = self._config.get('last_prepared_install')
        try:
            previous = json.loads((self._data_root() / 'desktop-ready.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        if not isinstance(previous, dict) or not self._game_dir:
            return
        files = previous.get('files')
        if (str(previous.get('game_dir', '')).casefold() == self._game_dir.casefold() and
                isinstance(files, list) and len(files) == 4 and all(
                    isinstance(row, list) and len(row) == 2 and all(type(value) is int for value in row) for row in files)):
            self._update_baseline = {'game_dir': self._game_dir, 'files': files}

    def check_game_update(self):
        """Observe local files only; polling never starts or stops a process."""
        with self._lock:
            if not self._update_baseline or self._busy or self._closing:
                return self._state()
            now = time.monotonic()
            if self._update_checked_at is not None and now - self._update_checked_at < 1:
                return self._state()
            self._update_checked_at = now
            try:
                current = installation_stamp(self._game_dir)
            except (OSError, ValueError):
                self._prepared = False
                self._update_candidate = None
                self._game_update = {'phase': 'waiting', 'message': '游戏文件暂不可读取，正在等待更新完成。', 'token': ''}
                return self._state()
            if current == self._update_baseline['files'] and self._is_prepared():
                self._prepared = True
                self._update_candidate = None
                self._game_update = {'phase': 'idle', 'message': '', 'token': ''}
                return self._state()
            self._prepared = False
            if (self._game_dir.casefold(), json.dumps(current)) in self._attempted_updates:
                return self._state()
            if current != self._update_candidate:
                self._update_candidate = current
                self._update_seen_at = now
                self._game_update = {'phase': 'waiting', 'message': '检测到游戏文件变化，正在等待更新完成。', 'token': secrets.token_hex(16)}
            elif now - self._update_seen_at >= 6:
                self._game_update.update(phase='ready', message='检测到游戏更新，空闲时将自动重新准备资料。')
            return self._state()

    def refresh_game_update(self, token):
        """Called after the launcher has checked that its editor is idle."""
        with self._lock:
            self._idle()
            if (self._mode == 'demo' or self._external_workbench or self._game_update['phase'] != 'ready' or
                    token != self._game_update['token'] or not token):
                return self._state()
            try:
                current = installation_stamp(self._game_dir)
            except (OSError, ValueError):
                current = None
            if current != self._update_candidate or current is None:
                self._update_checked_at = None
                return self.check_game_update()
            self._attempted_updates.add((self._game_dir.casefold(), json.dumps(current)))
            self._config['last_prepared_install'] = self._update_baseline
            write_config(self._config)
            self._game_update.update(phase='preparing', message='正在自动准备更新后的游戏资料。')
            def refresh():
                self._prepare()
                self._launch('game')
            return self._start(refresh, '检测到游戏更新，正在自动准备资料', automatic=True)

    def _idle(self):
        if self._busy or self._closing:
            raise ValueError('当前操作还在进行，请稍候。')

    def set_game(self, value):
        with self._lock:
            self._idle()
            if not isinstance(value, str) or len(value) > 4096:
                raise ValueError('请选择包含 ThePiper.exe 的游戏目录。')
            selected = Path(value.strip().strip('"')).expanduser().resolve()
            if not (selected / 'ThePiper.exe').is_file():
                raise ValueError('没有找到 ThePiper.exe，请选择游戏安装目录。')
            if self._active_url and str(selected) != self._game_dir:
                self._stop_service()
            self._game_dir = str(selected)
            self._config['game_dir'] = self._game_dir
            write_config(self._config)
            self._prepared = self._is_prepared()
            self._reset_update_watch()
            self._error = ''
            self._progress = {'percent': 100 if self._prepared else 0, 'stage': 'ready' if self._prepared else 'idle',
                              'message': '工坊准备就绪' if self._prepared else '已找到游戏，可以开始准备', 'detail': ''}
            return self._state()

    def choose_game(self):
        if not self._window:
            raise ValueError('文件选择窗口尚未准备好。')
        import webview
        selected = self._window.create_file_dialog(webview.FileDialog.FOLDER,
                                                   directory=self._game_dir or str(Path.home()))
        return self.set_game(selected[0]) if selected else self.status()

    def _start(self, work, message, automatic=False):
        with self._lock:
            self._idle()
            self._busy = True
            self._auto_prepare_active = automatic
            self._error = ''
            self._progress = {'percent': 4, 'stage': 'starting', 'message': message, 'detail': ''}
            def execute():
                try:
                    work()
                except Exception as exc:
                    with self._lock:
                        self._error = str(exc)
                        if automatic:
                            self._game_update.update(phase='failed', message='自动准备未完成，请查看原因后重试。')
                        self._progress.update(stage='error', message='这一步还没有完成', detail='可以重试，或打开日志查看详情。')
                finally:
                    with self._lock:
                        self._busy = False
                        self._auto_prepare_active = False
            self._worker = threading.Thread(target=execute, name='dawn-desktop-operation', daemon=True)
            self._worker.start()
            return self._state()

    def _environment(self, mode='game'):
        env = dict(os.environ)
        env.update(DAWN_HOME=str(USER_ROOT), DAWN_DATA_DIR=str(self._data_root(mode)),
                   DAWN_ASSET_DIR=str(self._path('asset_dir', 'web/assets')),
                   DAWN_DEMO='1' if mode == 'demo' else '0', PYTHONUTF8='1', PYTHONUNBUFFERED='1')
        if self._game_dir:
            env['PIPER_GAME_DIR'] = self._game_dir
        else:
            env.pop('PIPER_GAME_DIR', None)
        # The desktop uses its saved settings; inherited CLI save overrides must
        # not make a new packaged instance silently edit a different directory.
        env.pop('PIPER_SAVE_DIR', None)
        return env

    def _popen(self, command, **kwargs):
        options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        return subprocess.Popen(command, cwd=APP_ROOT, **options, **kwargs)

    def _progress_to(self, percent, stage, message, detail=''):
        with self._lock:
            self._progress = {'percent': percent, 'stage': stage, 'message': message, 'detail': detail}

    def prepare(self):
        if not self._game_dir:
            raise ValueError('先选择游戏目录，再开始准备。')
        with self._lock:
            self._idle()
            try:
                self._attempted_updates.add((self._game_dir.casefold(), json.dumps(installation_stamp(self._game_dir))))
            except (OSError, ValueError):
                pass
            self._game_update = {'phase': 'idle', 'message': '', 'token': ''}
            return self._start(self._prepare, '正在检查游戏版本')

    def _prepare(self):
        self._stop_service()
        self._prepared = False
        (self._data_root() / 'desktop-ready.json').unlink(missing_ok=True)
        begin_preparation(self._data_root())
        game = Path(self._game_dir)
        with (LOG_ROOT / 'prepare.log').open('w', encoding='utf-8') as log:
            log.write(f'Dawn Atelier {app_version()}\n')
            try:
                compatible = inspect_game(game)
            except (OSError, ValueError) as exc:
                log.write(f'Compatibility check failed: {exc}\n')
                raise
            initial_stamp = compatible['installation_stamp']
            log.write(f"Compatibility: {compatible['package_version']} / {compatible['profile']}\n")
            log.flush()
            self._progress_to(12, 'tables', '正在准备物品与游戏资料', '首次准备需要一点时间，请保持窗口开启。')
            self._prepare_process = self._popen(task_command('prepare', '--game-dir', self._game_dir),
                env=self._environment(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace')
            for line in self._prepare_process.stdout:
                log.write(line)
                log.flush()
                if '[2/3]' in line:
                    self._progress_to(55, 'catalogue', '正在整理中文图鉴', '关联物品、角色与存档字段。')
                elif '[3/3]' in line:
                    self._progress_to(76, 'artwork', '正在准备界面插画', '资源来自本机已安装的游戏。')
            result = self._prepare_process.wait()
            self._prepare_process = None
        if result != 0:
            raise ValueError('准备未完成，请打开日志文件夹查看 prepare.log，然后重试。')
        now = datetime.now(timezone.utc).isoformat(timespec='seconds')
        if installation_stamp(game) != initial_stamp:
            raise ValueError('准备过程中游戏文件发生更新，请重新准备。')
        receipt = {'game_dir': str(game.resolve()), 'compatibility': compatible, 'created': now,
                   'files': initial_stamp}
        data = self._data_root()
        (data / 'desktop-ready.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
        with self._lock:
            self._config = read_config()
            self._config['last_prepared'] = now
            self._config['last_prepared_install'] = {'game_dir': self._game_dir, 'files': initial_stamp}
            write_config(self._config)
            self._prepared = self._is_prepared()
            if not self._prepared:
                raise ValueError('准备结果缺少必要文件，请重试。')
            self._reset_update_watch()
        self._progress_to(100, 'ready', '准备完成，可以进入工坊', '今后双击打开即可继续使用。')

    def launch(self, mode):
        if mode not in ('game', 'demo'):
            raise ValueError('请选择游戏模式或演示模式。')
        if mode == 'game':
            self._prepared = self._is_prepared()
            if not self._prepared:
                raise ValueError('游戏资料还未准备好，或游戏版本已更新。请先重新准备。')
        if self._active_url and self._mode == mode and self._child and self._child.poll() is None:
            return self.status()
        return self._start(lambda: self._launch(mode), '正在打开你的工坊')

    def _launch(self, mode):
        self._stop_service()
        ready = LOG_ROOT / ('service-' + secrets.token_hex(8) + '.json')
        self._ready_file = ready
        port = str(self._config.get('desktop_port_' + mode) or (18767 if mode == 'demo' else 18766))
        command = task_command('serve', '--port', port, '--fallback-port', '--ready-file', str(ready))
        if mode == 'demo':
            command.append('--demo')
        launch_id = secrets.token_hex(24)
        environment = self._environment(mode)
        environment['DAWN_DESKTOP_SESSION'] = launch_id
        if self._window:
            location = urlparse(self._window.get_current_url())
            if location.scheme != 'http' or location.hostname != '127.0.0.1' or not location.port:
                raise ValueError('桌面窗口来源尚未就绪，请稍后重试。')
            environment['DAWN_DESKTOP_ORIGIN'] = f'http://127.0.0.1:{location.port}'
        else:
            environment.pop('DAWN_DESKTOP_ORIGIN', None)
        with (LOG_ROOT / ('workbench-' + mode + '.log')).open('ab') as log:
            self._child = self._popen(command, env=environment, stdout=log, stderr=log)
        opener = build_opener(ProxyHandler({}))
        for _ in range(240):
            if self._closing:
                self._stop_service()
                return
            if self._child.poll() is not None:
                raise ValueError('工作台未能启动，请打开日志文件夹查看 workbench-' + mode + '.log。')
            if ready.is_file():
                try:
                    info = json.loads(ready.read_text(encoding='utf-8'))
                    url = 'http://127.0.0.1:' + str(int(info['port']))
                    with opener.open(url + '/api/health', timeout=1) as response:
                        health = json.load(response)
                    if health.get('app') == 'dawn-atelier' and bool(health.get('demo')) == (mode == 'demo') and info.get('session') == launch_id:
                        with self._lock:
                            self._active_url = url
                            self._workbench_session = launch_id
                            self._mode = mode
                            self._config['desktop_port_' + mode] = info['port']
                            write_config(self._config)
                        self._progress_to(100, 'running', '演示工坊已打开' if mode == 'demo' else '工坊已打开')
                        return
                except (OSError, ValueError, KeyError):
                    pass
            time.sleep(.1)
        self._stop_service()
        raise ValueError('工作台启动超时，请打开日志查看详情。')

    def _stop_service(self):
        child = self._child
        if child and child.poll() is None:
            if self._ready_file and self._ready_file.is_file():
                info = json.loads(self._ready_file.read_text(encoding='utf-8'))
                request = Request('http://127.0.0.1:' + str(info['port']) + '/api/desktop-stop',
                                  data=b'{}', headers={'X-Dawn-Control': info['token']}, method='POST')
                with build_opener(ProxyHandler({})).open(request, timeout=5) as response:
                    response.read()
                try:
                    child.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    raise ValueError('工作台仍在完成当前操作，请稍候再关闭。') from None
            else:
                # No ready marker means request handlers were never available.
                child.terminate()
                child.wait(timeout=5)
        self._child = None
        self._active_url = None
        self._workbench_session = None
        self._external_workbench = False
        self._mode = None
        if self._ready_file:
            self._ready_file.unlink(missing_ok=True)
            self._ready_file = None

    def stop(self):
        with self._lock:
            self._idle()
            self._stop_service()
            return self._state()

    def open_folder(self, kind):
        folders = {'data': USER_ROOT, 'logs': LOG_ROOT,
                   'backups': self._data_root(self._mode or 'game') / 'backups',
                   'exports': self._data_root(self._mode or 'game') / 'modified-saves'}
        if kind not in folders:
            raise ValueError('未知文件夹。')
        folder = folders[kind]
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))
        return {'ok': True}

    def open_browser(self):
        if not self._active_url:
            raise ValueError('请先打开工坊。')
        self._external_workbench = True
        webbrowser.open(self._active_url)
        return {'ok': True}

    def open_help(self):
        webbrowser.open('https://github.com/X-Zero-L/dawn-atelier#下载安装')
        return {'ok': True}

    def _close(self):
        self._closing = True
        try:
            self._stop_service()
        except Exception:
            self._closing = False
            raise
        # Do not interrupt a preparation subprocess midway through writing its
        # local cache. Native closing is blocked while preparation is busy.
