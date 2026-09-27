"""Immutable application resources and the user's writable workspace."""

import json
import os
from pathlib import Path
import re
import sys

FROZEN = bool(getattr(sys, 'frozen', False))
APP_ROOT = Path(__file__).resolve().parent
if os.environ.get('DAWN_HOME'):
    USER_ROOT = Path(os.environ['DAWN_HOME']).expanduser().resolve()
elif FROZEN:
    USER_ROOT = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'DawnAtelier'
else:
    USER_ROOT = APP_ROOT
CONFIG_PATH = USER_ROOT / 'config.local.json'
LOG_ROOT = USER_ROOT / 'logs'


def read_config():
    if not CONFIG_PATH.exists():
        return {}
    value = json.loads(CONFIG_PATH.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('本机配置格式无效，请在数据文件夹中检查 config.local.json。')
    return value


def write_config(value):
    USER_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_PATH.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(CONFIG_PATH)


def app_version():
    return json.loads((APP_ROOT / 'version.json').read_text(encoding='utf-8'))['version']


def find_game(settings=None):
    settings = read_config() if settings is None else settings
    explicit = os.environ.get('PIPER_GAME_DIR') or settings.get('game_dir')
    if explicit:
        return Path(explicit).expanduser().resolve()
    steam_roots = []
    if os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as handle:
                steam_roots.append(Path(winreg.QueryValueEx(handle, 'SteamPath')[0]))
        except OSError:
            pass
        for base in ('PROGRAMFILES(X86)', 'PROGRAMFILES'):
            if os.environ.get(base):
                steam_roots.append(Path(os.environ[base]) / 'Steam')
    libraries = list(steam_roots)
    for steam in steam_roots:
        index = steam / 'steamapps/libraryfolders.vdf'
        if index.is_file():
            libraries += [Path(value.replace('\\\\', '\\')) for value in re.findall(r'"path"\s+"([^"]+)"', index.read_text(encoding='utf-8', errors='replace'))]
    for library in libraries:
        game = library / 'steamapps/common/The Piper Of Dawn'
        if (game / 'ThePiper.exe').is_file():
            return game.resolve()
    return USER_ROOT / '.game-not-configured'


def task_command(task, *arguments):
    """Fixed internal tasks also work when sys.executable is the packaged EXE."""
    if FROZEN:
        return [sys.executable, '--internal-task', task, *map(str, arguments)]
    return [sys.executable, '-X', 'utf8', str(APP_ROOT / 'desktop.py'), '--internal-task', task, *map(str, arguments)]
