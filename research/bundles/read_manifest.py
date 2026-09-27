"""Read the installed YooAsset OOY 2.0.0 manifest; no game files are changed."""
from pathlib import Path
import struct
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app_config import GAME_DIR, DATA_ROOT

DEFAULT_SOURCE = GAME_DIR / 'ThePiper_Data/StreamingAssets/yoo/Main'
DEFAULT_OUTPUT = DATA_ROOT / 'bundles'


def parse_manifest(data):
    if data[:4] != b'OOY\0':
        raise ValueError('Unsupported manifest signature')
    pos = 4

    def number(fmt):
        nonlocal pos
        size = struct.calcsize('<' + fmt)
        result = struct.unpack_from('<' + fmt, data, pos)[0]
        pos += size
        return result

    def string():
        nonlocal pos
        size = number('H')
        result = data[pos:pos + size].decode('utf-8')
        pos += size
        if pos > len(data):
            raise ValueError('Truncated manifest string')
        return result

    def strings():
        return [string() for _ in range(number('H'))]

    result = {'version': string()}
    if result['version'] != '2.0.0':
        raise ValueError('This reader supports OOY manifest 2.0.0 only')
    result.update(flags=[number('B'), number('B'), number('B'), number('i')],
                  pipeline=string(), package=string(), package_version=string())
    result['assets'] = [dict(address=string(), path=string(), guid=string(),
                             tags=strings(), bundle_id=number('i'))
                         for _ in range(number('i'))]
    result['bundles'] = [dict(bundle_id=i, name=string(), unity_crc=number('I'),
                              hash=string(), crc=string(), size=number('q'),
                              encrypted=bool(number('B')), tags=strings(),
                              depend_ids=[number('i') for _ in range(number('H'))])
                          for i in range(number('i'))]
    if pos != len(data):
        raise ValueError(f'Trailing manifest bytes: {len(data) - pos}')
    if any(not 0 <= a['bundle_id'] < len(result['bundles']) for a in result['assets']):
        raise ValueError('Invalid asset bundle index')
    return result


def main():
    version = (DEFAULT_SOURCE / 'PackageManifest_Main.version').read_text().strip()
    source = DEFAULT_SOURCE / f'PackageManifest_Main_{version}.bytes'
    manifest = parse_manifest(source.read_bytes())
    DEFAULT_OUTPUT.mkdir(parents=True, exist_ok=True)
    (DEFAULT_OUTPUT / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"Manifest: {len(manifest['assets'])} assets; {len(manifest['bundles'])} bundles; {version}")


if __name__ == '__main__':
    main()
