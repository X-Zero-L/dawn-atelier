"""Inspect or update The Piper of Dawn's saved gold, retaining other bytes."""

import argparse
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path


def varint(data, pos):
    value = 0
    for shift in range(0, 70, 7):
        if pos >= len(data):
            raise ValueError('Truncated varint')
        byte = data[pos]
        pos += 1
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, pos
    raise ValueError('Invalid varint')


def encode(value):
    if not 0 <= value < 2**63:
        raise ValueError('Gold must fit a nonnegative signed 64-bit integer')
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def fields(data):
    result = []
    pos = 0
    while pos < len(data):
        start = pos
        tag, pos = varint(data, pos)
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError('Invalid field number')
        tag_end = pos
        if wire == 0:
            payload_start = pos
            value, pos = varint(data, pos)
        elif wire == 2:
            size, pos = varint(data, pos)
            payload_start = pos
            pos += size
            value = data[payload_start:pos]
        elif wire in (1, 5):
            payload_start = pos
            pos += 8 if wire == 1 else 4
            value = data[payload_start:pos]
        else:
            raise ValueError(f'Unsupported wire type {wire}')
        if pos > len(data):
            raise ValueError('Truncated field')
        result.append(dict(number=number, wire=wire, start=start, tag_end=tag_end,
                           payload_start=payload_start, end=pos, value=value))
    return result


def unique(items):
    if len(items) != 1:
        raise ValueError(f'Expected one matching field, found {len(items)}')
    return items[0]


def locate(data):
    outer = unique([f for f in fields(data) if f['number'] == 7 and f['wire'] == 2])
    entries = []
    for item in fields(outer['value']):
        if item['number'] != 1 or item['wire'] != 2:
            continue
        contents = fields(item['value'])
        ids = [f for f in contents if f['number'] == 1 and f['wire'] == 0]
        if len(ids) == 1 and ids[0]['value'] == 901:
            amount = unique([f for f in contents if f['number'] == 2 and f['wire'] == 0])
            entries.append((outer, item, amount))
    return unique(entries)


def replace(data, field, payload):
    prefix = data[field['start']:field['tag_end']]
    if field['wire'] == 2:
        prefix += encode(len(payload))
    return data[:field['start']] + prefix + payload + data[field['end']:]


def change(data, new_raw):
    outer, item, amount = locate(data)
    new_item = replace(item['value'], amount, encode(new_raw))
    new_outer = replace(outer['value'], item, new_item)
    return replace(data, outer, new_outer)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('save', type=Path)
    parser.add_argument('--gold', type=int)
    parser.add_argument('--backup-dir', type=Path)
    args = parser.parse_args()
    data = args.save.read_bytes()
    raw = locate(data)[2]['value']
    report = {'path': str(args.save), 'raw_gold': raw,
              'gold': str(Decimal(raw) / 1000), 'sha256': hashlib.sha256(data).hexdigest()}
    if args.gold is not None:
        if args.backup_dir is None:
            parser.error('--backup-dir is required when modifying a save')
        new_raw = args.gold * 1000
        updated = change(data, new_raw)
        if locate(updated)[2]['value'] != new_raw or change(updated, raw) != data:
            raise ValueError('Gold-only round trip failed')
        args.backup_dir.mkdir(parents=True, exist_ok=True)
        backup = args.backup_dir / (args.save.name + '.' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.bak')
        with backup.open('xb') as output:
            output.write(data)
        if args.save.read_bytes() != data:
            raise RuntimeError('Save changed while preparing the edit; retry from a fresh read')
        args.save.write_bytes(updated)
        if args.save.read_bytes() != updated:
            raise RuntimeError('Save readback mismatch; original retained in backup')
        report.update(new_raw_gold=new_raw, new_gold=args.gold, backup=str(backup),
                      sha256_after=hashlib.sha256(updated).hexdigest(), gold_only_round_trip=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
