"""Bounded FlatBuffers reflection reader using the MCAP's BFBS schema.

Format reference: https://github.com/google/flatbuffers/blob/master/reflection/reflection.fbs
This is a file-format reader, independent of generated/private robot message code.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass


class DecodeError(ValueError):
    pass


# reflection.BaseType values are part of the public FlatBuffers wire format.
SCALARS = {1: 'B', 2: '?', 3: 'b', 4: 'B', 5: 'h', 6: 'H',
           7: 'i', 8: 'I', 9: 'q', 10: 'Q', 11: 'f', 12: 'd'}


class Buffer:
    def __init__(self, data: bytes):
        self.data = data

    def check(self, position: int, size: int):
        if position < 0 or size < 0 or position + size > len(self.data):
            raise DecodeError(f'truncated buffer: offset={position}, size={size}, bytes={len(self.data)}')

    def read(self, position: int, fmt: str):
        self.check(position, struct.calcsize('<' + fmt))
        return struct.unpack_from('<' + fmt, self.data, position)[0]

    def indirect(self, position: int):
        target = position + self.read(position, 'I')
        self.check(target, 4)
        return target

    def field(self, table: int, vtable_offset: int):
        vtable = table - self.read(table, 'i')
        length = self.read(vtable, 'H')
        self.check(vtable, length)
        if length < 4 or length % 2:
            raise DecodeError('invalid vtable length')
        if vtable_offset >= length:
            return None
        offset = self.read(vtable + vtable_offset, 'H')
        if not offset:
            return None
        object_length = self.read(vtable + 2, 'H')
        if offset >= object_length:
            raise DecodeError('field outside table')
        self.check(table + offset, 1)
        return table + offset

    def slot(self, table: int, slot: int, fmt: str, default=0):
        position = self.field(table, 4 + slot * 2)
        return default if position is None else self.read(position, fmt)

    def table(self, table: int, slot: int):
        position = self.field(table, 4 + slot * 2)
        return None if position is None else self.indirect(position)

    def string_at(self, position: int):
        start = self.indirect(position)
        length = self.read(start, 'I')
        if length > 32 * 1024 * 1024:
            raise DecodeError('string too large')
        self.check(start + 4, length + 1)
        if self.data[start + 4 + length] != 0:
            raise DecodeError('unterminated FlatBuffers string')
        try:
            return self.data[start + 4:start + 4 + length].decode('utf-8')
        except UnicodeDecodeError as error:
            raise DecodeError('invalid UTF-8 string') from error

    def string(self, table: int, slot: int, default=''):
        position = self.field(table, 4 + 2 * slot)
        return default if position is None else self.string_at(position)

    def tables(self, table: int, slot: int):
        vector = self.table(table, slot)
        if vector is None:
            return []
        count = self.read(vector, 'I')
        if count > 100_000:
            raise DecodeError('schema vector too large')
        self.check(vector + 4, count * 4)
        return [self.indirect(vector + 4 + i * 4) for i in range(count)]


@dataclass(frozen=True)
class Type:
    base: int
    element: int = 0
    index: int = -1
    length: int = 0


class Schema:
    def __init__(self, data: bytes):
        if data[4:8] != b'BFBS':
            raise DecodeError('FlatBuffers channel requires an embedded BFBS schema')
        b = Buffer(data)
        root = b.indirect(0)
        features = b.slot(root, 6, 'Q')
        if features & ~7:
            raise DecodeError(f'unsupported BFBS advanced features: {features}')
        objects = b.tables(root, 0)
        self.objects = []
        for obj in objects:
            fields = []
            for field in b.tables(obj, 1):
                if b.slot(field, 13, '?'):
                    raise DecodeError('64-bit offsets are not supported')
                type_pos = b.table(field, 1)
                if type_pos is None:
                    raise DecodeError('schema field has no type')
                fields.append(dict(
                    name=b.string(field, 0), type=self._type(b, type_pos),
                    offset=b.slot(field, 3, 'H'), integer=b.slot(field, 4, 'q'),
                    real=b.slot(field, 5, 'd'), optional=b.slot(field, 11, '?'),
                    required=b.slot(field, 7, '?'),
                ))
            self.objects.append(dict(name=b.string(obj, 0), fields=fields,
                                     struct=b.slot(obj, 2, '?'), size=b.slot(obj, 4, 'i')))
        root_obj = b.table(root, 4)
        if root_obj not in objects:
            raise DecodeError('schema has no valid root table')
        self.root = objects.index(root_obj)
        self.identifier = b.string(root, 2)
        self.unions = []
        for enum in b.tables(root, 1):
            values = {}
            for value in b.tables(enum, 1):
                type_pos = b.table(value, 3)
                if type_pos is not None:
                    values[b.slot(value, 1, 'q')] = self._type(b, type_pos)
            self.unions.append(values)

    @staticmethod
    def _type(b, pos):
        return Type(b.slot(pos, 0, 'b'), b.slot(pos, 1, 'b'),
                    b.slot(pos, 2, 'i', -1), b.slot(pos, 3, 'H'))

    def _object(self, index):
        if not 0 <= index < len(self.objects):
            raise DecodeError(f'invalid object index: {index}')
        return self.objects[index]

    def _size(self, type_):
        if type_.base in SCALARS:
            return struct.calcsize('<' + SCALARS[type_.base])
        if type_.base == 15:
            obj = self._object(type_.index)
            return obj['size'] if obj['struct'] else 4
        if type_.base == 17:
            return type_.length * self._size(Type(type_.element, index=type_.index))
        if type_.base in (13, 14, 16):
            return 4
        raise DecodeError(f'unsupported base type: {type_.base}')

    def decode(self, data: bytes):
        if self.identifier and data[4:8] != self.identifier.encode('ascii'):
            raise DecodeError('payload file identifier does not match schema')
        b = Buffer(data)
        return self._decode_object(b, b.indirect(0), self.root, 0)

    def _decode_object(self, b, pos, index, depth):
        if depth > 64:
            raise DecodeError('message nesting exceeds 64')
        obj = self._object(index)
        output = {}
        unions = []
        for field in obj['fields']:
            name, type_ = field['name'], field['type']
            location = pos + field['offset'] if obj['struct'] else b.field(pos, field['offset'])
            if type_.base == 16:
                unions.append((field, location))
                continue
            if location is None:
                if field['required']:
                    raise DecodeError(f'missing required field: {name}')
                if field['optional']:
                    value = None
                elif type_.base in SCALARS:
                    value = field['real'] if type_.base in (11, 12) else field['integer']
                    if type_.base == 2:
                        value = bool(value)
                else:
                    value = {13: '', 14: [], 17: []}.get(type_.base)
            else:
                value = self._value(b, location, type_, depth + 1)
            output[name] = value
        for field, location in unions:
            name, type_ = field['name'], field['type']
            discriminator = output.get(name + '_type', 0)
            if not discriminator:
                output[name] = None
                continue
            if not 0 <= type_.index < len(self.unions):
                raise DecodeError('invalid union index')
            actual = self.unions[type_.index].get(discriminator)
            if actual is None or location is None:
                raise DecodeError(f'invalid union value: {name}')
            output[name] = self._value(b, location, actual, depth + 1)
        return output

    def _value(self, b, position, type_, depth):
        if depth > 64:
            raise DecodeError('message nesting exceeds 64')
        kind = type_.base
        if kind in SCALARS:
            return b.read(position, SCALARS[kind])
        if kind == 13:
            return b.string_at(position)
        if kind == 15:
            obj = self._object(type_.index)
            start = position if obj['struct'] else b.indirect(position)
            return self._decode_object(b, start, type_.index, depth)
        if kind in (14, 17):
            if kind == 14:
                vector = b.indirect(position)
                count, start = b.read(vector, 'I'), vector + 4
            else:
                count, start = type_.length, position
            if count > 32 * 1024 * 1024:
                raise DecodeError('vector exceeds element limit')
            element = Type(type_.element, index=type_.index)
            stride = self._size(element)
            b.check(start, count * stride)
            if type_.element == 4:
                return b.data[start:start + count]
            # Avoid materializing millions of nested objects from a malformed schema.
            if count > 1_000_000:
                raise DecodeError('non-byte vector exceeds element limit')
            return [self._value(b, start + i * stride, element, depth + 1) for i in range(count)]
        raise DecodeError(f'unsupported FlatBuffers type: {kind}')
