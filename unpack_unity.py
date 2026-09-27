"""Extract UnityFS containers and TextAssets using only the Python standard library."""

import argparse
import json
import lzma
from pathlib import Path
import re
import struct
import zlib


class Reader:
    def __init__(self, data, endian='>'):
        self.data, self.pos, self.endian = data, 0, endian

    def take(self, count):
        if count < 0 or self.pos + count > len(self.data):
            raise ValueError(f'Read exceeds buffer at {self.pos}, size {count}')
        value = self.data[self.pos:self.pos + count]
        self.pos += count
        return value

    def unpack(self, fmt):
        return struct.unpack(self.endian + fmt, self.take(struct.calcsize(self.endian + fmt)))

    def one(self, fmt):
        return self.unpack(fmt)[0]

    def string(self):
        end = self.data.index(b'\0', self.pos)
        return self.take(end - self.pos + 1)[:-1].decode('utf-8', errors='replace')

    def align(self, amount=4):
        self.pos = (self.pos + amount - 1) // amount * amount

    def sized_string(self):
        result = self.take(self.one('i')).decode('utf-8', errors='replace')
        self.align()
        return result


def lz4_block(data, expected):
    out = bytearray()
    pos = 0
    while pos < len(data):
        token = data[pos]
        pos += 1
        length = token >> 4
        if length == 15:
            while True:
                extension = data[pos]
                pos += 1
                length += extension
                if extension != 255:
                    break
        out.extend(data[pos:pos + length])
        pos += length
        if pos == len(data):
            break
        if pos + 2 > len(data):
            raise ValueError('Truncated LZ4 match offset')
        offset = data[pos] | (data[pos + 1] << 8)
        pos += 2
        if not 0 < offset <= len(out):
            raise ValueError('Invalid LZ4 match offset')
        length = (token & 15) + 4
        if token & 15 == 15:
            while True:
                extension = data[pos]
                pos += 1
                length += extension
                if extension != 255:
                    break
        start = len(out) - offset
        if length <= offset:
            out.extend(out[start:start + length])
        else:
            pattern = bytes(out[start:])
            repeats, tail = divmod(length, offset)
            out.extend(pattern * repeats)
            out.extend(pattern[:tail])
        if len(out) > expected:
            raise ValueError('LZ4 output exceeds declared size')
    if len(out) != expected:
        raise ValueError(f'LZ4 output size {len(out)} != {expected}')
    return bytes(out)


def decompress(data, expected, flags):
    mode = flags & 63
    if mode == 0:
        output = data
    elif mode in (2, 3):
        output = lz4_block(data, expected)
    elif mode == 1:
        # Unity stores LZMA properties followed directly by the compressed stream.
        props, dictionary = struct.unpack('<BI', data[:5])
        lc, rem = props % 9, props // 9
        lp, pb = rem % 5, rem // 5
        output = lzma.decompress(data[5:], format=lzma.FORMAT_RAW, filters=[
            {'id': lzma.FILTER_LZMA1, 'dict_size': dictionary, 'lc': lc, 'lp': lp, 'pb': pb}
        ])
    else:
        raise ValueError(f'Unsupported Unity compression mode {mode}')
    if len(output) != expected:
        raise ValueError('Unity block decompressed size mismatch')
    return output


def bundle_files(data):
    r = Reader(data)
    if r.string() != 'UnityFS':
        raise ValueError('Input is not a decoded UnityFS bundle')
    version = r.one('I')
    player, engine = r.string(), r.string()
    total, compressed, plain, flags = r.unpack('QIII')
    if total != len(data):
        raise ValueError(f'UnityFS declared length {total} != {len(data)}')
    if version >= 7:
        r.align(16)
    if flags & 128:
        info = data[-compressed:]
    else:
        info = r.take(compressed)
    if flags & 512:
        r.align(16)
    info_reader = Reader(decompress(info, plain, flags))
    content_hash = info_reader.take(16).hex()
    blocks = [info_reader.unpack('IIH') for _ in range(info_reader.one('I'))]
    directories = []
    for _ in range(info_reader.one('I')):
        offset, size, file_flags = info_reader.unpack('QQI')
        directories.append({'name': info_reader.string(), 'offset': offset, 'size': size, 'flags': file_flags})
    content = bytearray()
    for size, packed, block_flags in blocks:
        content.extend(decompress(r.take(packed), size, block_flags))
    result = []
    for entry in directories:
        start, end = entry['offset'], entry['offset'] + entry['size']
        if end > len(content):
            raise ValueError('UnityFS directory exceeds content size')
        result.append((entry, bytes(content[start:end])))
    return {'format': version, 'player': player, 'engine': engine,
            'content_hash': content_hash, 'blocks': len(blocks),
            'uncompressed_crc32': zlib.crc32(content)}, result


def serialized_objects(data):
    r = Reader(data)
    metadata_size, file_size, version, data_offset = r.unpack('IIII')
    if not 9 <= version <= 23:
        raise ValueError(f'Unsupported serialized-file version {version}')
    endian = r.one('B')
    r.take(3)
    if version >= 22:
        metadata_size, file_size, data_offset, _ = r.unpack('IQQQ')
    if file_size != len(data):
        raise ValueError('Serialized file length does not match header')
    r.endian = '<' if endian == 0 else '>'
    unity_version = r.string()
    platform = r.one('i')
    type_tree = bool(r.one('?')) if version >= 13 else True
    types = []
    for _ in range(r.one('i')):
        class_id = r.one('i')
        stripped = r.one('?') if version >= 16 else False
        script_index = r.one('h') if version >= 17 else -1
        if version >= 13:
            if (version < 16 and class_id < 0) or (version >= 16 and class_id == 114):
                r.take(16)
            r.take(16)
        if type_tree:
            if version < 12:
                raise ValueError('Old recursive type trees are not supported')
            nodes, string_bytes = r.unpack('ii')
            r.take(nodes * (32 if version >= 19 else 24))
            r.take(string_bytes)
        if version >= 21:
            r.take(r.one('i') * 4)
        types.append({'class_id': class_id, 'script_index': script_index, 'stripped': stripped})
    if 7 <= version < 14:
        r.one('i')
    objects = []
    for _ in range(r.one('i')):
        if version >= 14:
            r.align()
            path_id = r.one('q')
        else:
            path_id = r.one('i')
        offset = r.one('q' if version >= 22 else 'I') + data_offset
        size, type_index = r.unpack('Ii')
        if version < 16:
            class_id = r.one('H')
        else:
            class_id = types[type_index]['class_id']
        if version < 11:
            r.one('H')
        if 11 <= version < 17:
            r.one('h')
        if version in (15, 16):
            r.one('B')
        if offset < data_offset or offset + size > len(data):
            raise ValueError('Serialized object exceeds data range')
        objects.append({'path_id': path_id, 'offset': offset, 'size': size,
                        'type_index': type_index, 'class_id': class_id})
    return {'format': version, 'unity_version': unity_version, 'platform': platform,
            'type_tree': type_tree, 'types': types}, objects, r.endian


def safe_name(value):
    value = value.replace('\\', '/').rsplit('/', 1)[-1]
    return re.sub(r'[\x00-\x1f<>:"/\\|?*]', '_', value)[:180] or 'unnamed'


def extract(bundle, destination, keep_containers=False):
    info, contents = bundle_files(bundle.read_bytes())
    record = {'bundle': str(bundle), **info, 'files': []}
    for entry, data in contents:
        file_record = dict(entry)
        record['files'].append(file_record)
        if keep_containers:
            output = destination / 'containers' / bundle.stem / safe_name(entry['name'])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
        if entry['name'].endswith(('.resS', '.resource')):
            continue
        try:
            metadata, objects, endian = serialized_objects(data)
        except (ValueError, IndexError, struct.error) as exc:
            file_record['parse_error'] = str(exc)
            continue
        file_record.update(metadata)
        file_record['objects'] = objects
        for obj in objects:
            if obj['class_id'] != 49:
                continue
            reader = Reader(data[obj['offset']:obj['offset'] + obj['size']], endian)
            name = reader.sized_string()
            payload = reader.take(reader.one('i'))
            output = destination / 'textassets' / bundle.stem / f"{obj['path_id']}_{safe_name(name)}.bytes"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(payload)
            obj.update(name=name, extracted=str(output), payload_bytes=len(payload))
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--keep-containers', action='store_true')
    args = parser.parse_args()
    paths = [args.source] if args.source.is_file() else sorted(args.source.rglob('*.bundle'))
    args.output.mkdir(parents=True, exist_ok=True)
    index = []
    for path in paths:
        try:
            record = extract(path, args.output, args.keep_containers)
            index.append(record)
            text_count = sum(1 for f in record['files'] for obj in f.get('objects', []) if obj.get('extracted'))
            print(json.dumps({'bundle': path.name, 'files': len(record['files']), 'textassets': text_count}), flush=True)
        except Exception as exc:
            index.append({'bundle': str(path), 'error': f'{type(exc).__name__}: {exc}'})
            print(json.dumps(index[-1]), flush=True)
    (args.output / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
