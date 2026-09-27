"""Inspect, export, or edit explicitly selected fields in a ThePiper save."""

import argparse
from datetime import datetime
import hashlib
import json
import struct
from pathlib import Path

from save_codec import ROOT, Schema
from app_config import BACKUP_ROOT


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_modified(source, original, modified, destination):
    if source.read_bytes() != original:
        raise RuntimeError('Source save changed since it was opened; reopen it first')
    backups = BACKUP_ROOT
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = backups / f'{source.name}.{stamp}.bak'
    with backup.open('xb') as output:
        output.write(original)
    if destination.exists() and destination.resolve() != source.resolve():
        raise FileExistsError('Output file exists; choose another filename')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.' + stamp + '.tmp')
    with temporary.open('xb') as output:
        output.write(modified)
    if temporary.read_bytes() != modified:
        raise RuntimeError('Staged file readback mismatch')
    if source.read_bytes() != original:
        raise RuntimeError('Source changed while staging the edit; staged copy retained')
    temporary.replace(destination)
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for verb in ('inspect', 'dump', 'edit'):
        command = commands.add_parser(verb)
        command.add_argument('save', type=Path)
        if verb == 'inspect':
            command.add_argument('--find', default='')
        else:
            command.add_argument('--output', type=Path, required=True)
        if verb == 'edit':
            command.add_argument('--set', action='append', required=True, metavar='FIELD_PATH=JSON_VALUE')
    args = parser.parse_args()
    schema = Schema()
    original = args.save.read_bytes()
    if args.command == 'inspect':
        leaves = [f for f in schema.leaves(original) if args.find.lower() in (f['path'] + str(f['value'])).lower()]
        print(json.dumps({'save': str(args.save), 'sha256': digest(original), 'fields': leaves}, ensure_ascii=False, indent=2))
    elif args.command == 'dump':
        document = schema.decode(original, 'SaveLoadSystem.GameSaveData')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'output': str(args.output), 'bytes': len(original), 'sha256': digest(original)}))
    else:
        modified = original
        edits = []
        existing = {f['path']: f for f in schema.leaves(original)}
        for assignment in args.set:
            path, separator, text = assignment.partition('=')
            if not separator or path not in existing:
                parser.error('Each --set needs an existing confirmed field path and a JSON value')
            value = json.loads(text)
            if existing[path]['type'] == 'float' and isinstance(value, (float, int)) and not isinstance(value, bool):
                value = struct.unpack('<f', struct.pack('<f', value))[0]
            modified = schema.edit(modified, path, value)
            edits.append({'path': path, 'before': existing[path]['value'], 'after': value})
        parsed = {f['path']: f for f in schema.leaves(modified)}
        for edit in edits:
            if parsed[edit['path']]['value'] != edit['after']:
                raise RuntimeError('Changed field did not decode to the requested value')
        reverted = modified
        for edit in reversed(edits):
            reverted = schema.edit(reverted, edit['path'], edit['before'])
        if reverted != original:
            raise RuntimeError('Unrelated save bytes changed; output was not written')
        backup = write_modified(args.save, original, modified, args.output)
        report = {'source': str(args.save), 'output': str(args.output), 'backup': str(backup),
                  'sha256_before': digest(original), 'sha256_after': digest(modified), 'edits': edits}
        report_path = BACKUP_ROOT / (backup.name + '.json')
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
