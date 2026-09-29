# -*- mode: python ; coding: utf-8 -*-
"""Explicit resource allowlist for the Windows desktop release.

Run through scripts/build-windows.py so metadata and dependency pins agree.
Never collect the repository root, data/, config.local.json, or web/assets/.
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

ROOT = Path(SPECPATH).resolve().parent
RESOURCE_FILES = [
    "web/index.html",
    "web/app.js",
    "web/presets-ui.js",
    "web/style.css",
    "web/presets.css",
    "web/progression-ui.js",
    "web/progression.css",
    "web/save-refresh.js",
    "web/brand/emblem.svg",
    "web/brand/botanical.svg",
    "desktop/index.html",
    "desktop/launcher.css",
    "desktop/launcher.js",
    "schemas/thepiper-2026-09-25/save_schema.json",
    "schemas/thepiper-2026-09-25/config_schema.json",
    "schemas/thepiper-2026-09-25/enums.json",
    "schemas/thepiper-2026-09-28/save_schema.json",
    "schemas/thepiper-2026-09-28/config_schema.json",
    "schemas/thepiper-2026-09-28/enums.json",
    "schemas/thepiper-2026-09-29/save_schema.json",
    "schemas/thepiper-2026-09-29/config_schema.json",
    "schemas/thepiper-2026-09-29/enums.json",
    "schemas/compatibility/2026-09-25-1016.json",
    "schemas/compatibility/2026-09-28-1042.json",
    "schemas/compatibility/2026-09-29-717.json",
    "version.json",
    "NOTICE.md",
    "build/assets/dawn-atelier.ico",
]
datas = []
for relative in RESOURCE_FILES:
    source = ROOT / relative
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"Missing or linked release resource: {relative}")
    datas.append((str(source), str(Path(relative).parent)))

# pywebview's official hook supplies its JavaScript bridge and native WebView2 DLLs.
datas += copy_metadata("pywebview")
datas += copy_metadata("pythonnet")
datas += copy_metadata("clr-loader")

hiddenimports = [
    "app_config", "app_paths", "desktop_service", "demo_data", "web_server", "game_runtime", "presets",
    "inventory", "favor", "compatibility", "native_layout", "piper_save", "save_codec", "gold_save", "prepare",
    "export_catalogue", "extract_web_art", "unpack_unity", "unpack",
    "read_manifest", "decode_bundles", "decode_tables", "extract_unity",
    "dump_currency", "inspect_meta", "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "app_update", "update_packages", "updates_install",
]

analysis = Analysis(
    [str(ROOT / "desktop.py")],
    pathex=[str(ROOT), str(ROOT / "research"), str(ROOT / "research/bundles")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "PySide6", "cefpython3", "gi", "Cocoa"],
    noarchive=False,
    optimize=0,
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="DawnAtelier",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / "build/assets/dawn-atelier.ico"),
    version=os.environ["DAWN_VERSION_FILE"],
    uac_admin=False,
    contents_directory="_internal",
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="DawnAtelier",
)
