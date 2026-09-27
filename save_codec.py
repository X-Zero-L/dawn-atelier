"""Schema-aware, byte-preserving codec for this game's protobuf-like data."""

import json
from pathlib import Path
import re
import struct

from app_config import APP_ROOT as ROOT, DATA_ROOT, SCHEMA_ROOT


def read_varint(data, position):
    value = 0
    for shift in range(0, 70, 7):
        if position >= len(data):
            raise ValueError('Truncated variable-length integer')
        byte = data[position]
        position += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, position
    raise ValueError('Invalid variable-length integer')


def encode_varint(value):
    if not 0 <= value <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError('Integer does not fit in 64 bits')
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def wire_fields(data):
    position = 0
    result = []
    while position < len(data):
        start = position
        tag, position = read_varint(data, position)
        tag_end = position
        number, wire = tag >> 3, tag & 7
        # The game's generated format deliberately includes tag zero in four records.
        if wire == 0:
            payload_start = position
            value, position = read_varint(data, position)
        elif wire == 2:
            length, position = read_varint(data, position)
            payload_start = position
            position += length
            value = data[payload_start:position]
        elif wire in (1, 5):
            payload_start = position
            position += 8 if wire == 1 else 4
            value = data[payload_start:position]
        else:
            raise ValueError(f'Unsupported wire type {wire} at byte {start}')
        if position > len(data):
            raise ValueError('Field extends beyond message')
        result.append(dict(tag=number, wire=wire, start=start, tag_end=tag_end,
                           payload_start=payload_start, end=position, value=value))
    return result


def replace_payload(data, field, payload):
    prefix = data[field['start']:field['tag_end']]
    if field['wire'] == 2:
        prefix += encode_varint(len(payload))
    return data[:field['start']] + prefix + payload + data[field['end']:]


def element_type(field):
    typ = field['type']
    if typ['kind'] == 'generic' and 'List`' in typ.get('name', ''):
        return typ['args'][0], True
    if typ['kind'] == 'array':
        return typ['element'], True
    return typ, False


class Schema:
    def __init__(self):
        self.types = {}
        self.source = None
        for name in ('save_schema.json', 'config_schema.json'):
            path = DATA_ROOT / 'schema' / name
            if not path.exists():
                path = SCHEMA_ROOT / name
            if path.exists():
                document = json.loads(path.read_text(encoding='utf-8'))
                self.source = document['source']
                self.types.update((typ['name'], typ) for typ in document['types'])
        if not self.types:
            raise FileNotFoundError('Extracted schemas are missing')

    def confirmed(self, type_name):
        typ = self.types.get(type_name)
        if typ is None:
            return {}
        return {f['protobuf_tag']: f for f in typ['fields'] if f.get('protobuf_tag') is not None
                and 'confirmed' in f.get('tag_status', '')}

    def scalar(self, field, typ):
        name = typ.get('name', '')
        value = field['value']
        if field['wire'] == 0:
            if name == 'bool':
                return bool(value)
            bits = {'int8': 8, 'int16': 16, 'int32': 32, 'int64': 64}.get(name)
            if typ['kind'] == 'enum':
                bits = 32
            if bits:
                value &= (1 << bits) - 1
                if value & (1 << (bits - 1)):
                    value -= 1 << bits
            return value
        if name == 'float' and field['wire'] == 5:
            return struct.unpack('<f', value)[0]
        if name == 'double' and field['wire'] == 1:
            return struct.unpack('<d', value)[0]
        if name == 'string' and field['wire'] == 2:
            return value.decode('utf-8')
        return {'_wire': field['wire'], '_hex': value.hex() if isinstance(value, bytes) else value}

    def decode(self, data, type_name, depth=0):
        if depth > 64:
            raise ValueError('Nested message depth exceeds 64')
        confirmed = self.confirmed(type_name)
        result = {}
        for wire in wire_fields(data):
            declaration = confirmed.get(wire['tag'])
            if declaration is None:
                key = f'@tag_{wire["tag"]}'
                value = wire['value']
                value = {'_wire': wire['wire'], '_hex': value.hex()} if isinstance(value, bytes) else value
                result.setdefault(key, []).append(value)
                continue
            typ, repeated = element_type(declaration)
            name = declaration['name']
            if typ['kind'] == 'message' and wire['wire'] == 2:
                value = self.decode(wire['value'], typ['name'], depth + 1)
            else:
                value = self.scalar(wire, typ)
            if repeated:
                result.setdefault(name, []).append(value)
            elif name in result:
                raise ValueError(f'Duplicate singular field {type_name}.{name}')
            else:
                result[name] = value
        return result

    def leaves(self, data, type_name='SaveLoadSystem.GameSaveData', prefix=''):
        confirmed = self.confirmed(type_name)
        counters = {}
        for wire in wire_fields(data):
            declaration = confirmed.get(wire['tag'])
            if declaration is None:
                continue
            typ, repeated = element_type(declaration)
            name = declaration['name']
            index = counters.get(name, 0)
            counters[name] = index + 1
            component = name + (f'[{index}]' if repeated else '')
            path = prefix + ('.' if prefix else '') + component
            if typ['kind'] == 'message' and wire['wire'] == 2:
                yield from self.leaves(wire['value'], typ['name'], path)
            else:
                value = self.scalar(wire, typ)
                if not isinstance(value, dict):
                    yield {'path': path, 'value': value, 'type': typ.get('name'),
                           'kind': typ['kind'], 'wire': wire['wire'], 'tag': wire['tag']}

    def edit(self, data, path, new_value, type_name='SaveLoadSystem.GameSaveData'):
        first, separator, rest = path.partition('.')
        match = re.fullmatch(r'([A-Za-z_][A-Za-z_0-9]*)(?:\[(\d+)\])?', first)
        if not match:
            raise ValueError(f'Invalid field path: {path}')
        name, index_text = match.groups()
        candidates = [f for f in self.confirmed(type_name).values() if f['name'] == name]
        if len(candidates) != 1:
            raise ValueError(f'Field is not confirmed: {type_name}.{name}')
        declaration = candidates[0]
        typ, repeated = element_type(declaration)
        matches = [f for f in wire_fields(data) if f['tag'] == declaration['protobuf_tag']]
        if repeated != (index_text is not None):
            raise ValueError('Repeated fields require an explicit [index]')
        index = int(index_text or 0)
        if index >= len(matches) or (not repeated and len(matches) != 1):
            raise ValueError('The selected field is not present in this save')
        wire = matches[index]
        if separator:
            if typ['kind'] != 'message' or wire['wire'] != 2:
                raise ValueError('Path attempts to enter a scalar field')
            payload = self.edit(wire['value'], rest, new_value, typ['name'])
        else:
            type_label = typ.get('name', '')
            if wire['wire'] == 0:
                if type_label == 'bool':
                    if not isinstance(new_value, bool):
                        raise ValueError('Boolean fields require true or false')
                    number = int(new_value)
                else:
                    if not isinstance(new_value, int) or isinstance(new_value, bool):
                        raise ValueError('Integer field requires an integer')
                    signed = type_label.startswith('int') or typ['kind'] == 'enum'
                    bits_match = re.search(r'(8|16|32|64)$', type_label)
                    bits = int(bits_match[1]) if bits_match else 32
                    minimum = -(1 << (bits - 1)) if signed else 0
                    maximum = (1 << (bits - int(signed))) - 1
                    if not minimum <= new_value <= maximum:
                        raise ValueError(f'Value outside {type_label} range')
                    number = new_value & 0xFFFFFFFFFFFFFFFF
                payload = encode_varint(number)
            elif type_label in ('float', 'double'):
                if not isinstance(new_value, (float, int)) or isinstance(new_value, bool):
                    raise ValueError('Floating-point field requires a number')
                payload = struct.pack('<f' if type_label == 'float' else '<d', new_value)
            elif type_label == 'string' and isinstance(new_value, str):
                payload = new_value.encode('utf-8')
            else:
                raise ValueError('Only confirmed scalar values can be edited')
        return replace_payload(data, wire, payload)
