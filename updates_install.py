"""Bounded, side-by-side desktop update handoff. Never replace the user's files."""

import argparse
import ctypes
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import time

from update_packages import parse_version, verify_installation


PARENT_TIMEOUT = 60
START_TIMEOUT = 90
_FORMAT = 'dawn-atelier-update-job-v1'
_CLEAR_ENV = {'DAWN_HOME', 'DAWN_DATA_DIR', 'DAWN_ASSET_DIR', 'DAWN_DEMO',
              'PIPER_GAME_DIR', 'PIPER_SAVE_DIR', 'WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'}


def _path(value, boundary=None):
    """Check every existing ancestor; resolve() alone would hide junctions."""
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('更新路径必须是完整的本地路径。')
    if any(part.endswith(('.', ' ')) or ':' in part for part in path.parts[1:]):
        raise ValueError('更新路径包含无效的 Windows 文件名。')
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('更新目录不能包含符号链接或目录联接。')
    if boundary is not None and (path == boundary or boundary not in path.parents):
        raise ValueError('更新文件超出了工坊的更新目录。')
    return path


def _owned(value, home, area=None):
    root = _path(home) / 'updates'
    return _path(value, root / area if area else root)


def _read(path):
    _path(path)
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('更新记录大小异常。')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('更新记录格式无效。')
    return value


def _write(path, value, home):
    _owned(path, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        _owned(path, home)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class _Parent:
    """Keep a Windows process handle so waiting cannot follow a reused PID."""

    def __init__(self, pid, expected=None):
        if os.name != 'nt':
            raise OSError('应用更新重启仅支持 Windows。')
        from ctypes import wintypes
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
        self.kernel.GetProcessTimes.restype = wintypes.BOOL
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.OpenProcess(0x100000 | 0x1000, False, pid)
        self.created = None
        if not self.handle:
            if ctypes.get_last_error() == 87:
                return  # The parent has already exited.
            raise ctypes.WinError(ctypes.get_last_error())
        stamps = [wintypes.FILETIME() for _ in range(4)]
        if not self.kernel.GetProcessTimes(self.handle, *(ctypes.byref(stamp) for stamp in stamps)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error
        self.created = (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime
        if expected is not None and self.created != expected:
            self.close()  # The recorded parent exited and its PID was reused.

    def wait(self, timeout):
        if not self.handle:
            return True
        result = self.kernel.WaitForSingleObject(self.handle, int(timeout * 1000))
        if result == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        return result == 0

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def _current_version(executable):
    _path(executable)
    if executable.name != 'DawnAtelier.exe':
        raise ValueError('自动更新仅适用于完整的 Windows 便携包。')
    version = _read(executable.parent / 'package-manifest.json')['version']
    parse_version(version)
    return version


def prepare_handoff(stage, home: Path, current_exe: Path, mode=None, browser=False) -> Path:
    home, current_exe = _path(home), _path(current_exe)
    new = _owned(stage['directory'], home)
    version = stage['version']
    previous_version = _current_version(current_exe)
    if parse_version(version) <= parse_version(previous_version):
        raise ValueError('待安装版本必须比当前版本更新。')
    if mode not in (None, 'game', 'demo') or not isinstance(browser, bool):
        raise ValueError('更新后的启动方式无效。')
    if not re.fullmatch('[0-9a-f]{64}', stage['sha256']):
        raise ValueError('下载校验记录无效。')
    verify_installation(new, version)
    manifest = verify_installation(current_exe.parent, previous_version, allow_extra=True)
    previous = home / 'updates/rollback' / (previous_version + '-' + secrets.token_hex(8)) / 'DawnAtelier'
    _owned(previous, home, 'rollback').mkdir(parents=True, exist_ok=False)
    # Only the distribution manifest defines the rollback copy. Adjacent saves,
    # logs, settings, or unrelated files in the user's directory are not copied.
    for name in [row['path'] for row in manifest['files']] + ['package-manifest.json']:
        source = _path(current_exe.parent / name, current_exe.parent)
        target = _owned(previous / name, home, 'rollback')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    verify_installation(previous, previous_version)
    parent = _Parent(os.getpid())
    try:
        job = home / 'updates/jobs' / (secrets.token_hex(16) + '.json')
        _write(job, {'format': _FORMAT, 'nonce': secrets.token_hex(32), 'parent_pid': os.getpid(),
                     'parent_created': parent.created, 'created': time.time(),
                     'directory': str(new), 'version': version, 'sha256': stage['sha256'],
                     'previous': str(previous), 'previous_version': previous_version,
                     'mode': mode, 'browser': browser}, home)
        return job
    finally:
        parent.close()


def _job(path, home):
    path = _owned(path, home, 'jobs')
    if path.parent != _path(home) / 'updates/jobs' or not re.fullmatch('[0-9a-f]{32}\\.json', path.name):
        raise ValueError('更新重启记录的路径无效。')
    job = _read(path)
    if (job.get('format') != _FORMAT or not re.fullmatch('[0-9a-f]{64}', str(job.get('nonce', '')))
            or type(job.get('parent_pid')) is not int or job['parent_pid'] <= 0
            or type(job.get('parent_created')) is not int
            or job.get('mode') not in (None, 'game', 'demo') or type(job.get('browser')) is not bool
            or not re.fullmatch('[0-9a-f]{64}', str(job.get('sha256', '')))):
        raise ValueError('更新重启记录无效。')
    new = _owned(job['directory'], home)
    previous = _owned(job['previous'], home, 'rollback')
    if new == previous or parse_version(job['version']) <= parse_version(job['previous_version']):
        raise ValueError('更新重启记录的版本无效。')
    return path, job, new, previous


def _launch(executable, home, flags):
    environment = {name: value for name, value in os.environ.items() if name.upper() not in _CLEAR_ENV}
    environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return subprocess.Popen([str(executable), '--home', str(home), *flags], cwd=str(executable.parent),
                            env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, close_fds=True)


def _mode_flags(job):
    return (['--resume', job['mode']] if job.get('mode') else []) + (['--browser'] if job.get('browser') else [])


def _notice(home, message, version=None, rollback=False):
    _write(_path(home) / 'updates/notice.json', {'message': message, 'version': version,
           'rollback': rollback, 'created': time.time()}, home)


def _mark_failed(home, version, failed=True):
    path = _path(home) / 'updates/failed.json'
    try:
        values = _read(path).get('versions', [])
    except (OSError, ValueError):
        values = []
    values = [value for value in values if isinstance(value, str)] if isinstance(values, list) else []
    versions = set(values)
    versions.add(version) if failed else versions.discard(version)
    _write(path, {'versions': sorted(versions)}, home)


def _stop_owned(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def run_handoff(job, home):
    home = _path(home)
    path, payload, new, previous = _job(job, home)
    verify_installation(new, payload['version'])
    verify_installation(previous, payload['previous_version'])
    # Exclusive ownership prevents two helpers from replaying the same job.
    with _owned(path.with_suffix('.claimed'), home).open('x', encoding='ascii') as claim:
        claim.write(str(os.getpid()))
    parent = _Parent(payload['parent_pid'], payload['parent_created'])
    try:
        _write(path.with_suffix('.helper-ready'), {'nonce': payload['nonce'], 'version': payload['version']}, home)
        if not parent.wait(PARENT_TIMEOUT):
            _notice(home, '旧窗口尚未退出，已取消本次重启。稍后可再次更新。', payload['version'])
            return False
    finally:
        parent.close()
    if _owned(path.with_suffix('.cancelled'), home).exists():
        _notice(home, '本次更新重启已取消，当前版本已保留。', payload['version'])
        return False
    child = None
    try:
        verify_installation(_owned(new, home), payload['version'])
        child = _launch(new / 'DawnAtelier.exe', home, ['--update-ticket', str(path), *_mode_flags(payload)])
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError('新版本在启动完成前退出。')
            receipt_path = _owned(path.with_suffix('.ready'), home)
            if receipt_path.exists():
                receipt = _read(receipt_path)
                if (not hmac.compare_digest(str(receipt.get('nonce', '')), payload['nonce'])
                        or receipt.get('version') != payload['version'] or receipt.get('pid') != child.pid
                        or receipt.get('directory') != str(new)):
                    raise ValueError('新版本的启动回执无效。')
                _mark_failed(home, payload['version'], failed=False)
                _write(home / 'updates/active.json', {'format': 'dawn-atelier-active-v1',
                       'successful': True, 'directory': str(new), 'version': payload['version'],
                       'sha256': payload['sha256'], 'previous': str(previous),
                       'previous_version': payload['previous_version']}, home)
                return True
            time.sleep(0.25)
        raise TimeoutError('新版本未能在 90 秒内完成启动。')
    except Exception as error:
        try:
            _mark_failed(home, payload['version'])
        except (OSError, ValueError):
            pass  # An unwritable status file must not prevent recovery.
        try:
            if child is not None:
                _stop_owned(child)
            verify_installation(_owned(previous, home, 'rollback'), payload['previous_version'])
            _launch(previous / 'DawnAtelier.exe', home, ['--skip-app-update', *_mode_flags(payload)])
            _notice(home, f'新版本启动失败，已返回上一版本。{error}', payload['version'], rollback=True)
        except Exception as rollback_error:
            _notice(home, f'新版本启动失败。请重新打开原来的工坊。{error}；{rollback_error}', payload['version'])
        return False


def acknowledge_start(job, home, current_exe, version):
    path, payload, new, _ = _job(job, home)
    if _path(current_exe) != new / 'DawnAtelier.exe' or version != payload['version']:
        raise ValueError('当前程序与更新重启记录不一致。')
    verify_installation(new, version)
    helper = _read(path.with_suffix('.helper-ready'))
    if not hmac.compare_digest(str(helper.get('nonce', '')), payload['nonce']):
        raise ValueError('更新助手未就绪。')
    _write(path.with_suffix('.ready'), {'nonce': payload['nonce'], 'version': version,
           'directory': str(new), 'pid': os.getpid()}, home)


def redirect_to_active(home, current_exe, arguments: list) -> bool:
    if any(arg.split('=', 1)[0] in ('--update-ticket', '--skip-app-update', '--internal-task') for arg in arguments):
        return False
    try:
        home, current_exe = _path(home), _path(current_exe)
        active_path = _owned(home / 'updates/active.json', home)
        if not active_path.exists():
            return False
        active = _read(active_path)
        if active.get('format') != 'dawn-atelier-active-v1' or active.get('successful') is not True:
            raise ValueError('缓存的更新尚未完成启动。')
        new = _owned(active['directory'], home)
        if new / 'DawnAtelier.exe' == current_exe:
            return False
        if parse_version(active['version']) <= parse_version(_current_version(current_exe)):
            return False
        failed_path = _owned(home / 'updates/failed.json', home)
        if failed_path.exists() and active['version'] in _read(failed_path).get('versions', []):
            return False
        verify_installation(new, active['version'])
        mode = 'demo' if '--demo' in arguments else None
        for index, argument in enumerate(arguments):
            if argument == '--resume' and index + 1 < len(arguments):
                value = arguments[index + 1]
            elif argument.startswith('--resume='):
                value = argument.partition('=')[2]
            else:
                continue
            if value in ('game', 'demo'):
                mode = value
        _launch(new / 'DawnAtelier.exe', home, _mode_flags({'mode': mode, 'browser': '--browser' in arguments}))
        return True
    except (OSError, ValueError, KeyError, TypeError) as error:
        try:
            _notice(home, f'缓存的新版本无法打开，已继续使用当前版本。{error}')
        except (OSError, ValueError):
            pass
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--job', type=Path, required=True)
    args = parser.parse_args()
    if not run_handoff(args.job, args.home):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
