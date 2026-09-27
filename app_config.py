"""Portable paths for installed game data and the self-contained demo."""

import json
import os
from pathlib import Path
import re
import sys

APP_ROOT = Path(__file__).resolve().parent
DEMO = '--demo' in sys.argv or os.environ.get('DAWN_DEMO') == '1'
_local_path = APP_ROOT / 'config.local.json'
_local = json.loads(_local_path.read_text(encoding='utf-8-sig')) if _local_path.exists() else {}


def configured_path(env_name, config_name, fallback):
    value = os.environ.get(env_name) or _local.get(config_name) or fallback
    path = Path(value).expanduser()
    return (APP_ROOT / path).resolve() if not path.is_absolute() else path.resolve()


def find_game():
    explicit = os.environ.get('PIPER_GAME_DIR') or _local.get('game_dir')
    if explicit:
        return Path(explicit).expanduser().resolve()
    steam_roots = []
    if os.name == 'nt':
        import winreg
        for key in (r'Software\Valve\Steam',):
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
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
    return APP_ROOT / '.game-not-configured'


GAME_DIR = find_game()
DATA_ROOT = configured_path('DAWN_DATA_DIR', 'data_dir', 'data/demo' if DEMO else 'data/game')
ASSET_ROOT = configured_path('DAWN_ASSET_DIR', 'asset_dir', 'web/assets')
BACKUP_ROOT = DATA_ROOT / 'backups'
MODIFIED_ROOT = DATA_ROOT / 'modified-saves'
SAVE_DIR = DATA_ROOT / 'saves' if DEMO else configured_path('PIPER_SAVE_DIR', 'save_dir', GAME_DIR / 'ThePiper_Data/SavesDir')
SCHEMA_ROOT = APP_ROOT / 'schemas/thepiper-2026-09-25'

if DEMO:
    from demo_data import prepare_demo
    prepare_demo(DATA_ROOT)
