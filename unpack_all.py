"""Fully decrypt and unpack every manifest bundle; preserve all resource payloads."""

import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'research/bundles'))
from decode_bundles import recover_constants, decode_bundle
from read_manifest import DEFAULT_SOURCE
from app_config import DATA_ROOT
from unpack_unity import bundle_files, serialized_objects, safe_name


def main():
    manifest = json.loads((DATA_ROOT / 'bundles/manifest.json').read_text(encoding='utf-8'))
    master, constants = recover_constants()
    output = DATA_ROOT / 'resources'
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for index, bundle in enumerate(manifest['bundles']):
        encrypted = (DEFAULT_SOURCE / (bundle['hash'] + '.bundle')).read_bytes()
        if len(encrypted) != bundle['size'] or struct.pack('<I', zlib.crc32(encrypted)).hex() != bundle['crc']:
            raise ValueError(f'Encrypted CRC/size mismatch: {bundle["name"]}')
        plain = decode_bundle(encrypted, bundle['name'], master)
        info, files = bundle_files(plain)
        if info['uncompressed_crc32'] != bundle['unity_crc']:
            raise ValueError(f'Decoded UnityCRC mismatch: {bundle["name"]}')
        folder = output / safe_name(bundle['name'])
        folder.mkdir(exist_ok=True)
        (DATA_ROOT / 'bundles' / safe_name(bundle['name'])).write_bytes(plain)
        record = {'bundle_id': bundle['bundle_id'], 'name': bundle['name'],
                  'source_file': bundle['hash'] + '.bundle', 'encrypted_bytes': len(encrypted),
                  'encrypted_sha256': hashlib.sha256(encrypted).hexdigest(),
                  'decoded_sha256': hashlib.sha256(plain).hexdigest(),
                  'unity_crc32': f'{info["uncompressed_crc32"]:08x}',
                  'manifest_unity_crc32': f'{bundle["unity_crc"]:08x}', 'files': []}
        for entry, data in files:
            destination = folder / safe_name(entry['name'])
            destination.write_bytes(data)
            row = {**entry, 'path': str(destination.relative_to(DATA_ROOT)),
                   'sha256': hashlib.sha256(data).hexdigest()}
            if not entry['name'].endswith(('.resS', '.resource')):
                try:
                    metadata, objects, endian = serialized_objects(data)
                    row.update(metadata)
                    row['objects'] = objects
                except Exception as exc:
                    row['object_index_error'] = str(exc)
            record['files'].append(row)
        records.append(record)
        (output / 'index.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'completed': index + 1, 'total': len(manifest['bundles']),
                          'bundle': bundle['name'], 'unpacked_bytes': sum(len(data) for _, data in files),
                          'crc_matched': True}), flush=True)
    report = {'bundles': len(records), 'encrypted_bytes': sum(x['encrypted_bytes'] for x in records),
              'unpacked_bytes': sum(f['size'] for x in records for f in x['files']),
              'serialized_objects': sum(len(f.get('objects', [])) for x in records for f in x['files']),
              'all_crc_matched': True, 'GameAssembly_sha256': constants['gameassembly_sha256'],
              'metadata_sha256': constants['metadata_sha256'],
              'object_index_errors': [f['path'] for x in records for f in x['files'] if f.get('object_index_error')]}
    (output / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
