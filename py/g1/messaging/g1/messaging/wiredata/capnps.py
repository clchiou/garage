"""Wire data in Cap'n Proto format.

For now, users are expected to define ``dataclass`` to match Cap'n Proto
schema.  Hopefully this does not result in ``dataclass`` that are too
cumbersome to use.
"""

__all__ = [
    'CapnpPackedWireData',
    'CapnpWireData',
]

import dataclasses
import datetime
import enum
import functools
import re

import capnp

from g1.bases import datetimes
from g1.bases.assertions import ASSERT

from g1.messaging import wiredata
from g1.messaging.wiredata import matchers

_PRIMITIVE_TYPES = (
    capnp.VoidType,
    # Numeric types.
    bool,
    enum.Enum,
    float,
    int,
    # String types.
    bytes,
    str,
)


class _BaseWireData(wiredata.WireData):

    # Subclass must overwrite these.
    _from_bytes = None
    _to_bytes = None

    def __init__(self, loader):
        self._loader = loader

    def _get_struct_schema(self, type_):
        key = '%s:%s' % (type_.__module__, type_.__qualname__)
        return self._loader.struct_schemas[key]

    def to_lower(self, message):
        ASSERT.predicate(message, wiredata.is_message)
        message_type = type(message)
        builder = capnp.MessageBuilder()
        self._encode_struct(
            builder.init_root(self._get_struct_schema(message_type)),
            message_type,
            message,
        )
        return self._to_bytes(builder)

    def to_upper(self, message_type, wire_message):
        ASSERT.predicate(message_type, wiredata.is_message_type)
        reader = self._from_bytes(wire_message)
        return self._decode(
            message_type,
            reader.get_root(self._get_struct_schema(message_type)),
        )

    def _encode_struct(self, builder, value_type, value):
        for field in dataclasses.fields(value_type):
            self._encode_field(
                builder,
                field.type,
                _snake_to_camel(field.name),
                getattr(value, field.name),
            )

    def _encode_list(self, builder, element_type, elements):
        for i, element in enumerate(elements):
            self._encode_field(builder, element_type, i, element)

    def _encode_tuple(self, builder, field_types, field_values):
        """Encode a tuple to a struct's fields."""
        keys = builder.schema.fields
        ASSERT(
            len(keys) == len(field_types) == len(field_values),
            'expect tuple value matches schema: {}, {}, {}',
            keys,
            field_types,
            field_values,
        )
        for field_type, key, value in zip(field_types, keys, field_values):
            self._encode_field(builder, field_type, key, value)

    def _encode_union(self, builder, member_types, value):
        ASSERT.equal(len(builder.schema.fields), len(member_types))
        for key, member_type in zip(builder.schema.fields, member_types):
            if isinstance(value, member_type):
                self._encode_field(builder, member_type, key, value)
                return
        ASSERT.unreachable(
            'no matching union member type: {!r}, {!r}', member_types, value
        )

    def _encode_field(self, builder, field_type, key, value):

        if matchers.is_recursive_type(field_type):

            if field_type.__origin__ is list:
                self._encode_list(
                    builder.init(key, len(value)),
                    field_type.__args__[0],
                    value,
                )

            elif field_type.__origin__ is tuple:
                self._encode_tuple(
                    builder.init(key),
                    field_type.__args__,
                    value,
                )

            elif matchers.is_union_type(field_type):

                if value is None:
                    return

                type_ = matchers.match_optional_type(field_type)
                if type_:
                    self._encode_field(builder, type_, key, value)
                    return

                self._encode_union(
                    builder.init(key),
                    field_type.__args__,
                    value,
                )

            else:
                ASSERT.unreachable(
                    'unsupported generic: {!r}, {!r}', field_type, key
                )

        elif wiredata.is_message(value):
            ASSERT.predicate(field_type, wiredata.is_message_type)
            self._encode_struct(builder.init(key), field_type, value)

        elif isinstance(value, datetime.datetime):
            ASSERT.issubclass(field_type, datetime.datetime)
            timestamp = value.timestamp()
            field = builder.schema.fields[key]
            if not field.type.is_float32() and not field.type.is_float64():
                timestamp = int(timestamp)
            builder[key] = timestamp

        elif isinstance(value, Exception):
            # We assume that an exception is either represented by a
            # void (union) field or by a struct field.
            field = builder.schema.fields[key]
            if field.type.is_void():
                builder[key] = capnp.VOID
            else:
                ASSERT.true(field.type.is_struct())
                self._encode_tuple(
                    builder.init(key),
                    tuple(map(type, value.args)),
                    value.args,
                )

        elif isinstance(value, _PRIMITIVE_TYPES):
            ASSERT.issubclass(field_type, _PRIMITIVE_TYPES)
            builder[key] = value

        else:
            ASSERT.unreachable(
                'unsupported field type: {!r}, {!r}', field_type, key
            )

    def _decode(self, value_type, reader):

        if matchers.is_recursive_type(value_type):

            if value_type.__origin__ is list:
                ASSERT.isinstance(reader, capnp.DynamicListReader)
                element_type = value_type.__args__[0]
                return [self._decode(element_type, e) for e in reader]

            elif value_type.__origin__ is tuple:
                ASSERT.isinstance(reader, capnp.DynamicStructReader)
                keys = reader.schema.fields
                ASSERT(
                    len(keys) == len(value_type.__args__),
                    'expect tuple type matches schema: {}, {}',
                    keys,
                    value_type.__args__,
                )
                return tuple(
                    self._decode(field_type, reader[key])
                    for field_type, key in zip(value_type.__args__, keys)
                )

            elif matchers.is_union_type(value_type):

                type_ = matchers.match_optional_type(value_type)
                if type_:
                    if reader is None:
                        return reader
                    else:
                        return self._decode(type_, reader)

                ASSERT.isinstance(reader, capnp.DynamicStructReader)
                ASSERT.equal(
                    len(reader.schema.fields),
                    len(value_type.__args__),
                )
                for key, member_type in zip(
                    reader.schema.fields,
                    value_type.__args__,
                ):
                    value = reader[key]
                    if value is not None:
                        return self._decode(member_type, value)
                return ASSERT.unreachable(
                    'no union member selected: {}, {!r}',
                    value_type.__args__,
                    reader,
                )

            else:
                return ASSERT.unreachable(
                    'unsupported generic: {!r}', value_type
                )

        elif wiredata.is_message_type(value_type):
            ASSERT.isinstance(reader, capnp.DynamicStructReader)
            return value_type(
                **{
                    f.name: \
                    self._decode(f.type, reader[_snake_to_camel(f.name)])
                    for f in dataclasses.fields(value_type)
                }
            )

        elif not isinstance(value_type, type):
            # Non-``type`` instance cannot be passed to ``issubclass``.
            return ASSERT.unreachable(
                'unsupported value type: {!r}', value_type
            )

        elif issubclass(value_type, datetime.datetime):
            return datetimes.utcfromtimestamp(
                ASSERT.isinstance(reader, (int, float))
            )

        elif issubclass(value_type, enum.Enum):
            return value_type(ASSERT.isinstance(reader, int))

        elif issubclass(value_type, Exception):
            if reader is capnp.VOID:
                args = ()
            else:
                ASSERT.isinstance(reader, capnp.DynamicStructReader)
                args = tuple(
                    # TODO: For now, let's assume struct fields are
                    # primitive typed; otherwise, we have to decode
                    # them, too.
                    ASSERT.isinstance(reader[key], _PRIMITIVE_TYPES)
                    for key in reader.schema.fields
                )
            return value_type(*args)

        elif issubclass(value_type, _PRIMITIVE_TYPES):
            if isinstance(reader, memoryview):
                return reader.tobytes()
            else:
                return ASSERT.isinstance(reader, value_type)

        else:
            return ASSERT.unreachable(
                'unsupported value type: {!r}', value_type
            )


_SNAKE_TO_CAMEL_PATTERN = re.compile(r'_(\w)')


@functools.lru_cache()
def _snake_to_camel(snake_case):
    return _SNAKE_TO_CAMEL_PATTERN.sub(
        lambda m: m.group(1).upper(),
        snake_case.lower(),
    )


class CapnpWireData(_BaseWireData):

    _from_bytes = capnp.MessageReader.from_message_bytes
    _to_bytes = staticmethod(capnp.MessageBuilder.to_message_bytes)


class CapnpPackedWireData(_BaseWireData):

    _from_bytes = capnp.MessageReader.from_packed_message_bytes
    _to_bytes = staticmethod(capnp.MessageBuilder.to_packed_message_bytes)
