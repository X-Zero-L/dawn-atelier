"""Lossless access to BlazBlue Entropy Effect's local LZ4/protobuf saves.

Only transport and the named model/pack containers are defined here. Game
rules belong to the adapter. Unknown fields and untouched model bytes survive
edits exactly; unchanged documents retain their original compressed bytes.
"""

from dataclasses import dataclass
import struct


MAGIC = b'\x04\x22\x4d\x18'
MAX_SAVE_SIZE = 64 * 1024 * 1024
_MASK = 0xFFFFFFFF


def _rotl(value, bits):
    return ((value << bits) | (value >> (32 - bits))) & _MASK


def xxh32(data):
    """The LZ4 frame checksum, with the standard zero seed."""
    p1, p2, p3, p4, p5 = 2654435761, 2246822519, 3266489917, 668265263, 374761393
    position, size = 0, len(data)
    if size >= 16:
        lanes = [(p1 + p2) & _MASK, p2, 0, (-p1) & _MASK]
        while position <= size - 16:
            for index in range(4):
                word = struct.unpack_from('<I', data, position)[0]
                position += 4
                lanes[index] = (_rotl((lanes[index] + word * p2) & _MASK, 13) * p1) & _MASK
        result = sum(_rotl(value, bits) for value, bits in zip(lanes, (1, 7, 12, 18))) & _MASK
    else:
        result = p5
    result = (result + size) & _MASK
    while position <= size - 4:
        word = struct.unpack_from('<I', data, position)[0]
        position += 4
        result = (_rotl((result + word * p3) & _MASK, 17) * p4) & _MASK
    for byte in data[position:]:
        result = (_rotl((result + byte * p5) & _MASK, 11) * p1) & _MASK
    result ^= result >> 15
    result = (result * p2) & _MASK
    result ^= result >> 13
    result = (result * p3) & _MASK
    return (result ^ (result >> 16)) & _MASK


def _block_size(descriptor):
    code = (descriptor >> 4) & 7
    if descriptor & 0x8F or code not in (4, 5, 6, 7):
        raise ValueError('Unsupported LZ4 block descriptor')
    return 1 << (8 + 2 * code)


def _decode_block(data, history, maximum):
    output = bytearray(history)
    start, position = len(output), 0

    def length(initial):
        nonlocal position
        result = initial
        if initial == 15:
            while True:
                if position >= len(data):
                    raise ValueError('Truncated LZ4 length')
                value = data[position]
                position += 1
                result += value
                if value != 255:
                    break
        return result

    while position < len(data):
        token = data[position]
        position += 1
        literals = length(token >> 4)
        if position + literals > len(data) or len(output) - start + literals > maximum:
            raise ValueError('Invalid LZ4 literal length')
        output += data[position:position + literals]
        position += literals
        if position == len(data):
            break
        if position + 2 > len(data):
            raise ValueError('Truncated LZ4 match offset')
        offset = struct.unpack_from('<H', data, position)[0]
        position += 2
        if not 0 < offset <= len(output):
            raise ValueError('Invalid LZ4 match offset')
        count = length(token & 15) + 4
        if len(output) - start + count > maximum:
            raise ValueError('LZ4 block exceeds its declared maximum')
        pattern = output[-offset:]
        output += (pattern * ((count + offset - 1) // offset))[:count]
    return bytes(output[start:])


@dataclass(frozen=True)
class SaveDocument:
    original: bytes
    payload: bytes
    flags: int
    block_descriptor: int

    def encode(self, payload):
        payload = bytes(payload)
        if payload == self.payload:
            return self.original
        if len(payload) > MAX_SAVE_SIZE:
            raise ValueError('Save exceeds the supported size limit')
        descriptor = bytes((self.flags, self.block_descriptor))
        if self.flags & 8:
            descriptor += struct.pack('<Q', len(payload))
        result = bytearray(MAGIC + descriptor + bytes(((xxh32(descriptor) >> 8) & 255,)))
        # Raw blocks are part of the LZ4 frame standard. This avoids a compressor
        # dependency and permits exact preservation of the protobuf payload.
        size = _block_size(self.block_descriptor)
        for position in range(0, len(payload), size):
            block = payload[position:position + size]
            result += struct.pack('<I', len(block) | 0x80000000) + block
            if self.flags & 16:
                result += struct.pack('<I', xxh32(block))
        result += b'\0\0\0\0'
        if self.flags & 4:
            result += struct.pack('<I', xxh32(payload))
        return bytes(result)


def decode_save(data):
    data = bytes(data)
    if len(data) > MAX_SAVE_SIZE or not data.startswith(MAGIC) or len(data) < 11:
        raise ValueError('Not a supported LZ4 save')
    flags, descriptor = data[4:6]
    if flags >> 6 != 1 or flags & 3:
        raise ValueError('Unsupported LZ4 version, reserved flags or dictionary')
    size, position = _block_size(descriptor), 6
    content_size = None
    if flags & 8:
        if len(data) < position + 9:
            raise ValueError('Truncated LZ4 content size')
        content_size = struct.unpack_from('<Q', data, position)[0]
        position += 8
        if content_size > MAX_SAVE_SIZE:
            raise ValueError('Save exceeds the supported size limit')
    if data[position] != (xxh32(data[4:position]) >> 8) & 255:
        raise ValueError('Invalid LZ4 header checksum')
    position += 1
    output = bytearray()
    while True:
        if position + 4 > len(data):
            raise ValueError('Truncated LZ4 block header')
        header = struct.unpack_from('<I', data, position)[0]
        position += 4
        if not header:
            break
        length, raw = header & 0x7FFFFFFF, bool(header & 0x80000000)
        if not length or length > size or position + length > len(data):
            raise ValueError('Invalid LZ4 block size')
        block = data[position:position + length]
        position += length
        if flags & 16:
            if position + 4 > len(data) or struct.unpack_from('<I', data, position)[0] != xxh32(block):
                raise ValueError('Invalid LZ4 block checksum')
            position += 4
        history = b'' if flags & 32 else bytes(output[-65536:])
        decoded = block if raw else _decode_block(block, history, size)
        if len(output) + len(decoded) > MAX_SAVE_SIZE:
            raise ValueError('Save exceeds the supported size limit')
        output += decoded
    payload = bytes(output)
    if content_size is not None and len(payload) != content_size:
        raise ValueError('LZ4 content size does not match the decoded save')
    if flags & 4:
        if position + 4 > len(data) or struct.unpack_from('<I', data, position)[0] != xxh32(payload):
            raise ValueError('Invalid LZ4 content checksum')
        position += 4
    if position != len(data):
        raise ValueError('Unexpected bytes after the LZ4 save')
    return SaveDocument(data, payload, flags, descriptor)


def read_varint(data, position):
    value = 0
    for shift in range(0, 70, 7):
        if position >= len(data):
            raise ValueError('Truncated protobuf integer')
        byte = data[position]
        position += 1
        if shift == 63 and byte > 1:
            raise ValueError('Protobuf integer exceeds 64 bits')
        value |= (byte & 127) << shift
        if byte < 128:
            return value, position
    raise ValueError('Invalid protobuf integer')


def encode_varint(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError('Expected an unsigned 64-bit integer')
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def wire_fields(data):
    position, result = 0, []
    while position < len(data):
        start = position
        key, position = read_varint(data, position)
        tag_end = position
        tag, wire = key >> 3, key & 7
        if not 0 < tag <= 0x1FFFFFFF:
            raise ValueError('Invalid protobuf field number')
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
            raise ValueError('Unsupported protobuf wire type')
        if position > len(data):
            raise ValueError('Protobuf field exceeds message size')
        result.append(dict(tag=tag, wire=wire, value=value, start=start,
                           tag_end=tag_end, payload_start=payload_start, end=position))
    return result


def field(data, tag, wire):
    matches = [item for item in wire_fields(data) if item['tag'] == tag]
    if len(matches) != 1 or matches[0]['wire'] != wire:
        raise ValueError(f'Expected one protobuf field {tag} with wire type {wire}')
    return matches[0]


def replace_payload(data, selected, value):
    prefix = data[selected['start']:selected['tag_end']]
    if selected['wire'] == 2:
        prefix += encode_varint(len(value))
    return data[:selected['start']] + prefix + value + data[selected['end']:]


def read_modules(payload):
    modules = {}
    for item in wire_fields(payload):
        if item['tag'] != 2:
            continue
        if item['wire'] != 2:
            raise ValueError('Invalid model container')
        entry = item['value']
        name = field(entry, 1, 2)['value'].decode('utf-8')
        if not name or name in modules:
            raise ValueError('Empty or duplicate model name')
        values = [value for value in wire_fields(entry) if value['tag'] == 2]
        if len(values) > 1 or values and values[0]['wire'] != 2:
            raise ValueError('Invalid model payload')
        modules[name] = values[0]['value'] if values else b''
    if not modules:
        raise ValueError('No named models in the save')
    return modules


def replace_module(payload, name, value):
    read_modules(payload)
    for item in wire_fields(payload):
        if item['tag'] == 2 and field(item['value'], 1, 2)['value'].decode('utf-8') == name:
            selected = field(item['value'], 2, 2)
            return replace_payload(payload, item, replace_payload(item['value'], selected, value))
    raise ValueError(f'Model is absent: {name}')


def read_pack(module):
    """Read ID/count rows from the confirmed item and currency pack shape."""
    pack = field(module, 1, 2)['value']
    result, ids = [], set()
    for entry in wire_fields(pack):
        if entry['tag'] != 1:
            continue
        if entry['wire'] != 2:
            raise ValueError('Invalid pack entry')
        item_id = field(entry['value'], 1, 0)['value']
        value = field(entry['value'], 2, 2)['value']
        if item_id in ids or field(value, 1, 0)['value'] != item_id:
            raise ValueError('Duplicate or mismatched pack ID')
        count = field(value, 2, 0)['value']
        ids.add(item_id)
        result.append({'id': item_id, 'count': count})
    return result


def set_pack_count(module, item_id, count):
    """Patch an existing count; callers must enforce the game's value rules."""
    if not isinstance(item_id, int) or isinstance(item_id, bool):
        raise ValueError('Pack ID must be an integer')
    encoded = encode_varint(count)
    if item_id not in {row['id'] for row in read_pack(module)}:
        raise ValueError('Only existing pack entries can be edited')
    wrapper = field(module, 1, 2)
    pack = wrapper['value']
    for entry in wire_fields(pack):
        if entry['tag'] != 1 or field(entry['value'], 1, 0)['value'] != item_id:
            continue
        value = field(entry['value'], 2, 2)
        updated = replace_payload(value['value'], field(value['value'], 2, 0), encoded)
        updated = replace_payload(entry['value'], value, updated)
        return replace_payload(module, wrapper, replace_payload(pack, entry, updated))
    raise ValueError('Pack entry is absent')
