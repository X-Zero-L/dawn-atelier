"""Locate IL2CPP tables by validated PE/metadata structure, independent of RVAs."""

import struct


class NativeLayout:
    def __init__(self, assembly, metadata):
        self.assembly, self.metadata = assembly, metadata
        if len(metadata) < 256 or struct.unpack_from('<II', metadata) != (0xFAB11BAF, 31):
            raise ValueError('不支持的 IL2CPP 元数据格式。')
        header = struct.unpack_from('<64I', metadata)
        self.tables = [header[2 + i * 2:4 + i * 2] for i in range(31)]
        for offset, size in self.tables:
            if offset < 0 or size < 0 or offset + size > len(metadata):
                raise ValueError('游戏元数据表超出文件范围。')
        if self.tables[19][1] % 88:
            raise ValueError('游戏类型定义格式发生变化。')
        self.type_count = self.tables[19][1] // 88
        pe = struct.unpack_from('<I', assembly, 60)[0]
        if assembly[:2] != b'MZ' or assembly[pe:pe + 4] != b'PE\0\0' or struct.unpack_from('<H', assembly, pe + 4)[0] != 0x8664:
            raise ValueError('游戏程序集不是有效的 Windows x64 文件。')
        if struct.unpack_from('<H', assembly, pe + 24)[0] != 0x20B:
            raise ValueError('游戏程序集 PE 格式不受支持。')
        self.image_base = struct.unpack_from('<Q', assembly, pe + 48)[0]
        sections, optional_size = struct.unpack_from('<H', assembly, pe + 6)[0], struct.unpack_from('<H', assembly, pe + 20)[0]
        self.sections = []
        for index in range(sections):
            start = pe + 24 + optional_size + index * 40
            name = assembly[start:start + 8].rstrip(b'\0').decode('ascii')
            virtual_size, rva, size, raw = struct.unpack_from('<4I', assembly, start + 8)
            flags = struct.unpack_from('<I', assembly, start + 36)[0]
            if raw + size > len(assembly):
                raise ValueError('游戏程序集节区超出文件范围。')
            self.sections.append((name, rva, virtual_size, raw, size, flags))
        self.types_count, self.types_pointer, self.field_offsets = self._registration()
        self.method_count, self.methods_pointer = self._module()
        self._type_names = {}
        self._byval = {self.type_definition(index)[2]: index for index in range(self.type_count)}

    def offset(self, address, size=1):
        for _, rva, _, raw, length, _ in self.sections:
            relative = address - self.image_base - rva
            if 0 <= relative and relative + size <= length:
                return raw + relative
        raise ValueError('原生数据地址不在已映射文件节区中。')

    def address(self, offset):
        for _, rva, _, raw, length, _ in self.sections:
            if raw <= offset < raw + length:
                return self.image_base + rva + offset - raw
        raise ValueError('文件偏移不在原生节区中。')

    def read(self, address, fmt):
        return struct.unpack_from(fmt, self.assembly, self.offset(address, struct.calcsize(fmt)))

    def executable(self, address):
        return any(self.image_base + rva <= address < self.image_base + rva + length and flags & 0x20000000
                   for _, rva, _, _, length, flags in self.sections)

    def find(self, needle):
        position = -1
        while True:
            position = self.assembly.find(needle, position + 1)
            if position < 0:
                return
            yield position

    def string(self, index):
        start, length = self.tables[2]
        if not 0 <= index < length:
            raise ValueError('元数据字符串索引无效。')
        end = self.metadata.find(b'\0', start + index, start + length)
        if end < 0:
            raise ValueError('元数据字符串未结束。')
        return self.metadata[start + index:end].decode('utf-8')

    def type_definition(self, index):
        if not 0 <= index < self.type_count:
            raise ValueError('元数据类型索引无效。')
        return struct.unpack_from('<16i8H2I', self.metadata, self.tables[19][0] + index * 88)

    def type_name(self, index):
        if index not in self._type_names:
            definition = self.type_definition(index)
            if definition[3] >= 0 and definition[3] in self._byval:
                value = self.type_name(self._byval[definition[3]]) + '.' + self.string(definition[0])
            else:
                value = '.'.join(filter(None, [self.string(definition[1]), self.string(definition[0])]))
            self._type_names[index] = value
        return self._type_names[index]

    def fields(self, index):
        definition = self.type_definition(index)
        offset_table = self.read(self.field_offsets + index * 8, '<Q')[0]
        result = []
        for ordinal, field_index in enumerate(range(definition[8], definition[8] + definition[18])):
            name, type_index, _ = struct.unpack_from('<3i', self.metadata, self.tables[11][0] + field_index * 12)
            result.append({'name': self.string(name), 'type': self.type_shape(type_index),
                           'offset': self.read(offset_table + ordinal * 4, '<i')[0]})
        return result

    def methods(self, index):
        definition = self.type_definition(index)
        result = []
        for method_index in range(definition[9], definition[9] + definition[16]):
            row = struct.unpack_from('<7i4H', self.metadata, self.tables[5][0] + method_index * 36)
            token_index = (row[6] & 0xffffff) - 1
            result.append({'name': self.string(row[0]), 'argc': row[10], 'static': bool(row[7] & 16),
                           'return': self.type_shape(row[2]),
                           'address': self.read(self.methods_pointer + token_index * 8, '<Q')[0]
                           if 0 <= token_index < self.method_count else 0})
        return result

    def type_shape(self, index):
        if not 0 <= index < self.types_count:
            raise ValueError('元数据字段类型索引无效。')
        return self._type_shape(self.read(self.types_pointer + index * 8, '<Q')[0])

    def _type_shape(self, pointer, depth=0):
        if depth > 12:
            raise ValueError('元数据类型嵌套超出范围。')
        value, flags = self.read(pointer, '<QI')
        kind = (flags >> 16) & 255
        primitives = {1:'void',2:'bool',3:'char',4:'int8',5:'uint8',6:'int16',7:'uint16',8:'int32',9:'uint32',
                      10:'int64',11:'uint64',12:'float',13:'double',14:'string',24:'intptr',25:'uintptr',28:'object'}
        if kind in primitives:
            return primitives[kind]
        if kind in (0x11, 0x12):
            return self.type_name(value)
        if kind == 0x15:
            generic_type, instance = self.read(value, '<QQ')
            count, _, argv = self.read(instance, '<IIQ')
            if count > 32:
                raise ValueError('元数据泛型参数超出范围。')
            return [self._type_shape(generic_type, depth + 1),
                    [self._type_shape(self.read(argv + 8 * part, '<Q')[0], depth + 1) for part in range(count)]]
        if kind in (0xf, 0x10, 0x1d):
            return [kind, self._type_shape(value, depth + 1)]
        if kind == 0x14:
            element, rank = self.read(value, '<QB')
            return [kind, rank, self._type_shape(element, depth + 1)]
        return [kind, value]

    def schema_contract(self):
        result = {}
        defaults = {field: (typ, offset) for field, typ, offset in struct.iter_unpack(
            '<iii', self.metadata[self.tables[7][0]:sum(self.tables[7])])}
        for index in range(self.type_count):
            name = self.type_name(index)
            if not name.startswith(('SaveLoadSystem.', 'Example.')):
                continue
            result[name] = {'fields': self.fields(index),
                            'methods': [{key: value for key, value in method.items() if key != 'address'}
                                        for method in self.methods(index)]}
            definition = self.type_definition(index)
            if definition[24] & 2:
                constants = {}
                for field in range(definition[8], definition[8] + definition[18]):
                    if field not in defaults or defaults[field][1] < 0:
                        continue
                    type_index, offset = defaults[field]
                    kind = self.type_shape(type_index)
                    position = self.tables[8][0] + offset
                    if kind in ('int32', 'uint32'):
                        first = self.metadata[position]
                        length = 1 if first < 128 else 2 if first < 192 else 4 if first < 224 else 5 if first == 240 else 1 if first >= 254 else 0
                    else:
                        length = {'bool':1,'int8':1,'uint8':1,'int16':2,'uint16':2,'int64':8,'uint64':8}.get(kind, 0)
                    if not length or offset + length > self.tables[8][1]:
                        raise ValueError('枚举常量格式不受支持。')
                    field_name = self.string(struct.unpack_from('<i', self.metadata, self.tables[11][0] + field * 12)[0])
                    constants[field_name] = self.metadata[position:position + length].hex()
                result[name]['constants'] = constants
        return result

    def _registration(self):
        result = []
        needle = struct.pack('<Q', self.type_count)
        for position in self.find(needle):
            if position < 80 or position + 48 > len(self.assembly) or self.assembly[position + 16:position + 24] != needle:
                continue
            entries = struct.unpack_from('<16Q', self.assembly, position - 80)
            count, types, fields, sizes = entries[6], entries[7], entries[11], entries[13]
            if not self.type_count <= count <= 1000000:
                continue
            try:
                self.offset(types, count * 8)
                self.offset(fields, self.type_count * 8)
                self.offset(sizes, self.type_count * 8)
                valid = 0
                for index in range(min(32, count)):
                    pointer = self.read(types + index * 8, '<Q')[0]
                    kind = (self.read(pointer, '<QI')[1] >> 16) & 255
                    valid += kind in range(1, 0x46)
                if valid == min(32, count):
                    result.append((count, types, fields))
            except (ValueError, struct.error):
                continue
        if len(set(result)) != 1:
            raise ValueError('无法唯一定位游戏类型表，需要适配此版本。')
        return result[0]

    def _module(self):
        result = []
        for name_offset in self.find(b'Assembly-CSharp.dll\0'):
            try:
                pointer = self.address(name_offset)
            except ValueError:
                continue
            for module in self.find(struct.pack('<Q', pointer)):
                if module + 24 > len(self.assembly):
                    continue
                count, methods = struct.unpack_from('<QQ', self.assembly, module + 8)
                if not 100 <= count <= 1000000:
                    continue
                try:
                    self.offset(methods, count * 8)
                    pointers = self.read(methods, '<32Q')
                    if all(not address or self.executable(address) for address in pointers) and any(pointers):
                        result.append((count, methods))
                except (ValueError, struct.error):
                    continue
        if len(set(result)) != 1:
            raise ValueError('无法唯一定位游戏方法表，需要适配此版本。')
        return result[0]
