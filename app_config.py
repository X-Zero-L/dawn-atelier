"""Portable paths for installed game data and the self-contained demo."""

import os
from pathlib import Path
import sys
from app_paths import APP_ROOT, USER_ROOT, read_config, find_game

DEMO = '--demo' in sys.argv or os.environ.get('DAWN_DEMO') == '1'
_local = read_config()


def configured_path(env_name, config_name, fallback):
    value = os.environ.get(env_name) or _local.get(config_name) or fallback
    path = Path(value).expanduser()
    return (USER_ROOT / path).resolve() if not path.is_absolute() else path.resolve()


GAME_DIR = find_game(_local)
DATA_ROOT = configured_path('DAWN_DATA_DIR', 'data_dir', 'data/demo' if DEMO else 'data/game')
ASSET_ROOT = configured_path('DAWN_ASSET_DIR', 'asset_dir', 'web/assets')
BACKUP_ROOT = DATA_ROOT / 'backups'
MODIFIED_ROOT = DATA_ROOT / 'modified-saves'
SAVE_DIR = DATA_ROOT / 'saves' if DEMO else configured_path('PIPER_SAVE_DIR', 'save_dir', GAME_DIR / 'ThePiper_Data/SavesDir')
SCHEMA_ROOT = APP_ROOT / 'schemas/thepiper-2026-09-25'

if DEMO:
    from demo_data import prepare_demo
    prepare_demo(DATA_ROOT)
