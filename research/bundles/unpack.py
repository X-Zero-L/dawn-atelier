"""Extract gameplay tables and inventory all encrypted bundles without changing the game.

Run from any directory: python research/bundles/unpack.py
"""
from pathlib import Path
import hashlib
import json
import struct
import sys
import zlib
from read_manifest import DEFAULT_SOURCE, DEFAULT_OUTPUT, parse_manifest
from decode_bundles import recover_constants, decode_bundle
from decode_tables import public_numbers, decode_table
from extract_unity import unpack, textassets, Reader
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from gold_save import fields


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    destination = DEFAULT_OUTPUT
    destination.mkdir(parents=True, exist_ok=True)
    source = DEFAULT_SOURCE
    version = (source / 'PackageManifest_Main.version').read_text().strip()
    manifest_path = source / f'PackageManifest_Main_{version}.bytes'
    manifest = parse_manifest(manifest_path.read_bytes())
    master, crypto_evidence = recover_constants()
    evidence = {'package_version': version, 'manifest_sha256': sha256(manifest_path.read_bytes()),
                'asset_count': len(manifest['assets']), 'bundle_count': len(manifest['bundles']),
                'crypto': crypto_evidence, 'bundle_headers': [], 'decoded_bundles': [], 'tables': []}
    manifest_assets = {Path(a['path']).stem: a['path'] for a in manifest['assets'] if a['bundle_id'] == 177}
    for bundle in manifest['bundles']:
        path = source / (bundle['hash'] + '.bundle')
        if path.stat().st_size != bundle['size']:
            raise ValueError(f'Bundle size mismatch: {path.name}')
        with path.open('rb') as stream:
            encrypted_header = stream.read(64)
        header = decode_bundle(encrypted_header, bundle['name'], master)
        reader = Reader(header)
        signature = reader.z()
        if signature != 'UnityFS':
            raise ValueError(f'Unsupported decoded header: {bundle["name"]}')
        format_version, unity, revision = reader.u('I'), reader.z(), reader.z()
        if reader.u('Q') != bundle['size']:
            raise ValueError(f'UnityFS declared size mismatch: {bundle["name"]}')
        evidence['bundle_headers'].append(dict(bundle_id=bundle['bundle_id'], name=bundle['name'],
                                               file=path.name, bytes=bundle['size'], signature=signature,
                                               format_version=format_version, unity_revision=revision))
        if bundle['bundle_id'] not in (0, 1, 177):
            continue
        encrypted = path.read_bytes()
        if struct.pack('<I', zlib.crc32(encrypted)).hex() != bundle['crc']:
            raise ValueError(f'Encrypted bundle CRC mismatch: {path.name}')
        plain = decode_bundle(encrypted, bundle['name'], master)
        (destination / bundle['name']).write_bytes(plain)
        evidence['decoded_bundles'].append(dict(name=bundle['name'], encrypted_sha256=sha256(encrypted),
                                                plain_sha256=sha256(plain), bytes=len(plain),
                                                encrypted_crc32=bundle['crc']))
        if bundle['bundle_id'] != 177:
            continue
        key = public_numbers()
        for directory in ('tables', 'tables-decoded'):
            (destination / directory).mkdir(exist_ok=True)
        serialized_crc = 0
        for node_name, serialized in unpack(plain).items():
            if Path(node_name).name != node_name:
                raise ValueError('Unexpected archive node path')
            serialized_crc = zlib.crc32(serialized, serialized_crc)
            (destination / node_name).write_bytes(serialized)
            for name, content, path_id in textassets(serialized):
                if Path(name).name != name:
                    raise ValueError('Unexpected TextAsset path')
                (destination / 'tables' / (name + '.bytes')).write_bytes(content)
                decoded = decode_table(content, key)
                count = struct.unpack_from('<I', decoded)[0]
                top = fields(decoded[4:])
                keys = [f for f in top if f['number'] == 1]
                rows = [f for f in top if f['number'] == 2 and f['wire'] == 2]
                if len(top) != count * 2 or len(keys) != count or len(rows) != count:
                    raise ValueError(f'Table row-count mismatch: {name}')
                # Parse each row to account for the complete protobuf wire payload.
                for row in rows:
                    fields(row['value'])
                (destination / 'tables-decoded' / (name + '.bytes')).write_bytes(decoded)
                evidence['tables'].append(dict(name=name, asset_path=manifest_assets.get(name),
                                                rows=count, encrypted_bytes=len(content),
                                                decoded_bytes=len(decoded), path_id=path_id,
                                                decoded_sha256=sha256(decoded),
                                                row_key_type='string' if keys and keys[0]['wire'] == 2 else 'integer'))
        evidence['serialized_crc32'] = f'{serialized_crc:08x}'
        evidence['manifest_unity_crc32'] = f'{bundle["unity_crc"]:08x}'
        if serialized_crc != bundle['unity_crc']:
            raise ValueError('Decoded serialized data CRC does not match manifest UnityCRC')
    evidence['tables'].sort(key=lambda t: t['name'])
    evidence['table_count'] = len(evidence['tables'])
    evidence['row_count'] = sum(t['rows'] for t in evidence['tables'])
    for name, obj in (('manifest.json', manifest), ('extraction-evidence.json', evidence)):
        (destination / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding='utf-8')
    lines = ['# Extracted gameplay tables', '', '| Table | Rows | Key |', '| --- | ---: | --- |']
    lines += [f"| {t['name']} | {t['rows']} | {t['row_key_type']} |" for t in evidence['tables']]
    (destination / 'TABLES.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: evidence[k] for k in ('package_version', 'asset_count', 'bundle_count', 'table_count', 'row_count', 'serialized_crc32', 'manifest_unity_crc32')}, indent=2))


if __name__ == '__main__':
    main()
