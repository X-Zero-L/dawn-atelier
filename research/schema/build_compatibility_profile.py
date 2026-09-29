"""Record native-confirmed serializer fingerprints for a reviewed build.

Usage: python research/schema/build_compatibility_profile.py --evidence path.json
       --version 2026-09-28-1042 --schema thepiper-2026-09-28 --output path.json
Only hashes and public schema identities are written, never game bytes.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from native_layout import NativeLayout
from app_paths import find_game


def digest(value):
    return hashlib.sha256(value).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--schema', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    game = find_game()
    assembly = (game / 'GameAssembly.dll').read_bytes()
    metadata = (game / 'ThePiper_Data/il2cpp_data/Metadata/global-metadata.dat').read_bytes()
    evidence = json.loads(args.evidence.read_text(encoding='utf-8'))
    if evidence['source']['GameAssembly_sha256'] != digest(assembly) or evidence['source']['global_metadata_sha256'] != digest(metadata):
        raise ValueError('Evidence belongs to a different game build.')
    layout = NativeLayout(assembly, metadata)
    names = {layout.type_name(index): index for index in range(layout.type_count)}
    probes = []
    for row in evidence['types']:
        if row.get('status') != 'complete_native_mapping':
            raise ValueError('Incomplete native serializer evidence: ' + row['name'])
        start, stop = int(row['rva'], 0), int(row['end_rva'], 0)
        methods = layout.methods(names[row['name']])
        matching = [(ordinal, method) for ordinal, method in enumerate(methods) if method['address'] == layout.image_base + start]
        if len(matching) != 1 or not 0 < stop - start < 1000000:
            raise ValueError('Ambiguous serializer identity: ' + row['name'])
        ordinal, method = matching[0]
        offset = layout.offset(layout.image_base + start, stop - start)
        probes.append({'type': row['name'], 'ordinal': ordinal, 'method': method['name'],
                       'length': stop - start, 'sha256': digest(assembly[offset:offset + stop - start])})
    if len(probes) < 250:
        raise ValueError('Incomplete native serializer evidence.')
    contract = json.dumps(layout.schema_contract(), sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    profile = {'id': args.version, 'schema': args.schema, 'metadata_version': 31,
               'GameAssembly_sha256': digest(assembly), 'global_metadata_sha256': digest(metadata),
               'contract_sha256': digest(contract), 'serializers': probes}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Recorded {len(probes)} native serializers for {args.version}.')


if __name__ == '__main__':
    main()
