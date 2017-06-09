__all__ = [
    'MessageBuilder',
    'MessageReader',

    'DynamicEnum',
    'DynamicList',
    'DynamicStruct',
]

import collections
import enum
import os

from . import bases
from . import io
from . import native
from .schemas import Schema
from .schemas import Type


class MessageBase:

    def __init__(self, make_context):
        self._make_context = make_context
        self._context = None
        self._resource = None

    def __enter__(self):
        assert self._make_context is not None
        assert self._resource is None
        self._context = self._make_context()
        self._make_context = None  # _make_context is one-time use only.
        self._resource = self._context.__enter__()
        return self

    def __exit__(self, *args):
        self._resource = None
        self._context, context = None, self._context
        return context.__exit__(*args)

    @property
    def canonical(self):
        assert self._resource is not None
        return self._resource.isCanonical()


class MessageReader(MessageBase):

    @classmethod
    def from_bytes(cls, blob):
        return cls(lambda: io.make_bytes_reader(blob))

    @classmethod
    def from_packed_bytes(cls, blob):
        return cls(lambda: io.make_packed_bytes_reader(blob))

    @classmethod
    def from_file(cls, path):
        return cls(lambda: io.make_file_reader(path))

    @classmethod
    def from_packed_file(cls, path):
        return cls(lambda: io.make_packed_file_reader(path))

    def get_root(self, schema):
        assert self._resource is not None
        assert schema.kind is Schema.Kind.STRUCT
        return DynamicStruct(schema, self._resource.getRoot(schema._schema))


class MessageBuilder(MessageBase):

    def __init__(self):
        super().__init__(io.make_bytes_builder)

    def init_root(self, schema):
        assert self._resource is not None
        assert schema.kind is Schema.Kind.STRUCT
        message = self._resource.initRoot(schema._schema)
        return DynamicStruct.Builder(schema, message)

    def to_bytes(self):
        assert self._resource is not None
        with io.make_bytes_writer() as writer:
            native.writeMessage(writer, self._resource)
            return writer.getArray()

    def to_packed_bytes(self):
        assert self._resource is not None
        with io.make_bytes_writer() as writer:
            native.writePackedMessage(writer, self._resource)
            return writer.getArray()

    def to_file(self, path):
        assert self._resource is not None
        with io.open_fd(path, os.O_WRONLY) as fd:
            native.writeMessageToFd(fd, self._resource)

    def to_packed_file(self, path):
        assert self._resource is not None
        with io.open_fd(path, os.O_WRONLY) as fd:
            native.writePackedMessageToFd(fd, self._resource)

    @staticmethod
    def _get_fd(file_like):
        try:
            return file_like.fileno()
        except OSError:
            return None

    def write_to(self, output):
        assert self._resource is not None
        fd = self._get_fd(output)
        if fd is None:
            output.write(self.to_bytes())
        else:
            native.writeMessageToFd(fd, self._resource)

    def write_packed_to(self, output):
        assert self._resource is not None
        fd = self._get_fd(output)
        if fd is None:
            output.write(self.to_packed_bytes())
        else:
            native.writePackedMessageToFd(fd, self._resource)


class DynamicEnum:

    @classmethod
    def from_member(cls, schema, member):
        assert schema.kind is Schema.Kind.ENUM
        if isinstance(member, enum.Enum):
            enumerant = schema.get_enumerant_from_ordinal(member.value)
        else:
            assert isinstance(member, int)
            enumerant = schema.get_enumerant_from_ordinal(member)
        if enumerant is None:
            raise ValueError('%r is not a member of %s' % (member, schema))
        return cls(schema, native.DynamicEnum(enumerant._enumerant))

    def __init__(self, schema, enum_):
        assert schema.kind is Schema.Kind.ENUM
        assert schema.id == enum_.getSchema().getProto().getId()
        self.schema = schema
        self._enum = enum_

        enumerant = self._enum.getEnumerant()
        if enumerant is None:
            self.enumerant = None
        else:
            self.enumerant = self.schema[enumerant.getProto().getName()]

    def get(self):
        return self._enum.getRaw()

    def __str__(self):
        raw = self.get()
        if raw == self.enumerant.ordinal:
            return self.enumerant.name
        else:
            return str(raw)

    __repr__ = bases.repr_object


class DynamicList(collections.Sequence):

    class Builder(collections.MutableSequence):

        def __init__(self, schema, list_):
            assert schema.kind is Schema.Kind.LIST
            assert schema.id == bases.list_schema_id(list_.getSchema())
            self.schema = schema
            self._list = list_

        def as_reader(self):
            return DynamicList(self.schema, self._list.asReader())

        def __len__(self):
            return self._list.size()

        def _ensure_index(self, index):
            if not isinstance(index, int):
                raise TypeError('non-integer index: %s' % index)
            if not 0 <= index < self._list.size():
                raise IndexError(
                    'not 0 <= %d < %d' % (index, self._list.size()))

        def __getitem__(self, index):
            self._ensure_index(index)
            return _dynamic_value_builder_to_python(
                self.schema.element_type,
                self._list[index],
            )

        def init(self, index, size):
            self._ensure_index(index)
            assert self.schema.element_type.kind is Type.Kind.LIST
            return DynamicList.Builder(
                self.schema.element_type.schema,
                self._list.init(index, size).asList(),
            )

        def __setitem__(self, index, value):
            self._ensure_index(index)
            _set_scalar(self._list, index, self.schema.element_type, value)

        def __delitem__(self, index):
            cls = self.__class__
            raise IndexError('%s.%s does not support __delitem__' %
                             (cls.__module__, cls.__qualname__))

        def insert(self, index, value):
            self[index] = value

        def __str__(self):
            return '[%s]' % ', '.join(map(bases.str_value, self))

        __repr__ = bases.repr_object

    def __init__(self, schema, list_):
        assert schema.kind is Schema.Kind.LIST
        assert schema.id == bases.list_schema_id(list_.getSchema())
        self.schema = schema
        self._list = list_
        self._values_cache = None

    @property
    def _values(self):
        if self._values_cache is None:
            self._values_cache = tuple(
                _dynamic_value_reader_to_python(
                    self.schema.element_type,
                    self._list[i],
                )
                for i in range(self._list.size())
            )
        return self._values_cache

    def __len__(self):
        return self._list.size()

    def __iter__(self):
        yield from self._values

    def __getitem__(self, index):
        return self._values[index]

    def __str__(self):
        return '[%s]' % ', '.join(map(bases.str_value, self._values))

    __repr__ = bases.repr_object


class DynamicStruct(collections.Mapping):

    class Builder(collections.MutableMapping):

        def __init__(self, schema, struct):
            assert schema.kind is Schema.Kind.STRUCT
            assert schema.id == struct.getSchema().getProto().getId()
            self.schema = schema
            self._struct = struct

        @property
        def total_size(self):
            msg_size = self._struct.totalSize()
            return (msg_size.wordCount, msg_size.capCount)

        def as_reader(self):
            return DynamicStruct(self.schema, self._struct.asReader())

        def __len__(self):
            count = 0
            for field in self.schema.fields:
                if self._struct.has(field._field):
                    count += 1
            return count

        def __contains__(self, name):
            field = self.schema.get(name)
            return field and self._struct.has(field._field)

        def __iter__(self):
            for field in self.schema.fields:
                if self._struct.has(field._field):
                    yield field.name

        def __getitem__(self, name):
            return self._get(name, True, None)

        def get(self, name, default=None):
            return self._get(name, False, default)

        def _get(self, name, raise_on_missing, default):
            field = self.schema.get(name)
            if field and self._struct.has(field._field):
                return _dynamic_value_builder_to_python(
                    field.type,
                    self._struct.get(field._field),
                )
            if raise_on_missing:
                raise KeyError(name)
            else:
                return default

        def init(self, name, size=None):

            field = self.schema[name]  # This may raise KeyError.

            if field.type.kind is Type.Kind.LIST:
                assert isinstance(size, int) and size > 0
                return DynamicList.Builder(
                    field.type.schema,
                    self._struct.init(field._field, size).asList(),
                )

            elif field.type.kind is Type.Kind.STRUCT:
                assert size is None
                return DynamicStruct.Builder(
                    field.type.schema,
                    self._struct.init(field._field).asStruct(),
                )

            else:
                raise AssertionError(
                    'cannot init non-list, non-struct field: %s' % field)

        def __setitem__(self, name, value):
            field = self.schema[name]  # This may raise KeyError.
            _set_scalar(self._struct, field._field, field.type, value)

        def __delitem__(self, name):
            field = self.schema[name]  # This may raise KeyError.
            self._struct.clear(field._field)

        def __str__(self):
            return '(%s)' % ', '.join(
                '%s = %s' % (name, bases.str_value(value))
                for name, value in self.items()
            )

        __repr__ = bases.repr_object

    def __init__(self, schema, struct):
        assert schema.kind is Schema.Kind.STRUCT
        assert schema.id == struct.getSchema().getProto().getId()
        self.schema = schema
        self._struct = struct
        self._dict_cache = None

    @property
    def _dict(self):
        if self._dict_cache is None:
            self._dict_cache = collections.OrderedDict(
                (
                    field.name,
                    _dynamic_value_reader_to_python(
                        field.type,
                        self._struct.get(field._field),
                    ),
                )
                for field in self.schema.fields
                if self._struct.has(field._field)
            )
        return self._dict_cache

    @property
    def total_size(self):
        msg_size = self._struct.totalSize()
        return (msg_size.wordCount, msg_size.capCount)

    def __len__(self):
        return len(self._dict)

    def __contains__(self, name):
        return name in self._dict

    def __iter__(self):
        yield from self._dict

    def __getitem__(self, name):
        return self._dict[name]

    def get(self, name, default=None):
        return self._dict.get(name, default)

    def __str__(self):
        return '(%s)' % ', '.join(
            '%s = %s' % (name, bases.str_value(value))
            for name, value in self._dict.items()
        )

    __repr__ = bases.repr_object


_SCALAR_SCHEMA_KINDS = frozenset((
    Schema.Kind.PRIMITIVE,
    Schema.Kind.BLOB,
    Schema.Kind.ENUM,
))


def _set_scalar(builder, key, type_, python_value):
    if type_.kind is Type.Kind.VOID:
        assert python_value is None
    elif type_.kind.schema_kind not in _SCALAR_SCHEMA_KINDS:
        raise TypeError('not scalar type: %s' % type_)
    elif type_.kind is Type.Kind.ENUM:
        python_value = DynamicEnum.from_member(type_.schema, python_value)
    builder.set(key, _python_to_dynamic_value_reader(type_, python_value))


# type_kind -> python_type, maker, converter
_DYNAMIC_VALUE_READER_TABLE = {

    Type.Kind.VOID: (
        type(None),
        native.DynamicValue.Reader.fromVoid,
        native.DynamicValue.Reader.asVoid,
    ),

    Type.Kind.BOOL: (
        bool,
        native.DynamicValue.Reader.fromBool,
        native.DynamicValue.Reader.asBool,
    ),

    Type.Kind.INT8: (
        int,
        native.DynamicValue.Reader.fromInt,
        native.DynamicValue.Reader.asInt,
    ),
    Type.Kind.INT16: (
        int,
        native.DynamicValue.Reader.fromInt,
        native.DynamicValue.Reader.asInt,
    ),
    Type.Kind.INT32: (
        int,
        native.DynamicValue.Reader.fromInt,
        native.DynamicValue.Reader.asInt,
    ),
    Type.Kind.INT64: (
        int,
        native.DynamicValue.Reader.fromInt,
        native.DynamicValue.Reader.asInt,
    ),

    Type.Kind.UINT8: (
        int,
        native.DynamicValue.Reader.fromInt,
        native.DynamicValue.Reader.asUInt,
    ),
    Type.Kind.UINT16: (
        int,
        native.DynamicValue.Reader.fromInt,
        native.DynamicValue.Reader.asUInt,
    ),
    Type.Kind.UINT32: (
        int,
        native.DynamicValue.Reader.fromInt,
        native.DynamicValue.Reader.asUInt,
    ),
    Type.Kind.UINT64: (
        int,
        native.DynamicValue.Reader.fromInt,
        native.DynamicValue.Reader.asUInt,
    ),

    Type.Kind.FLOAT32: (
        float,
        native.DynamicValue.Reader.fromFloat,
        native.DynamicValue.Reader.asFloat,
    ),
    Type.Kind.FLOAT64: (
        float,
        native.DynamicValue.Reader.fromFloat,
        native.DynamicValue.Reader.asFloat,
    ),

    Type.Kind.TEXT: (
        str,
        native.DynamicValue.Reader.fromStr,
        native.DynamicValue.Reader.asText,
    ),
    Type.Kind.DATA: (
        bytes,
        native.DynamicValue.Reader.fromBytes,
        native.DynamicValue.Reader.asData,
    ),

    Type.Kind.LIST: (
        DynamicList,
        native.DynamicValue.Reader.fromList,
        native.DynamicValue.Reader.asList,
    ),

    Type.Kind.ENUM: (
        DynamicEnum,
        native.DynamicValue.Reader.fromEnum,
        native.DynamicValue.Reader.asEnum,
    ),

    Type.Kind.STRUCT: (
        DynamicStruct,
        native.DynamicValue.Reader.fromStruct,
        native.DynamicValue.Reader.asStruct,
    ),
}


_DYNAMIC_READER_TYPES = frozenset((
    DynamicList,
    DynamicEnum,
    DynamicStruct,
))


def _python_to_dynamic_value_reader(type_, python_value):
    python_type, maker, _ = _DYNAMIC_VALUE_READER_TABLE[type_.kind]
    assert isinstance(python_value, python_type)
    if python_type is DynamicEnum:
        return maker(python_value._enum)
    elif python_type is DynamicList:
        return maker(python_value._list)
    elif python_type is DynamicStruct:
        return maker(python_value._struct)
    else:
        return maker(python_value)


def _dynamic_value_reader_to_python(type_, value):
    assert isinstance(value, native.DynamicValue.Reader)
    python_type, _, converter = _DYNAMIC_VALUE_READER_TABLE[type_.kind]
    python_value = converter(value)
    if python_type in _DYNAMIC_READER_TYPES:
        assert type_.schema is not None
        python_value = python_type(type_.schema, python_value)
    assert isinstance(python_value, python_type), (python_value, python_type)
    return python_value


# type_kind -> python_type, converter
_DYNAMIC_VALUE_BUILDER_TABLE = {

    Type.Kind.VOID: (type(None), lambda _: None),

    Type.Kind.BOOL: (bool, native.DynamicValue.Builder.asBool),

    Type.Kind.INT8: (int, native.DynamicValue.Builder.asInt),
    Type.Kind.INT16: (int, native.DynamicValue.Builder.asInt),
    Type.Kind.INT32: (int, native.DynamicValue.Builder.asInt),
    Type.Kind.INT64: (int, native.DynamicValue.Builder.asInt),

    Type.Kind.UINT8: (int, native.DynamicValue.Builder.asUInt),
    Type.Kind.UINT16: (int, native.DynamicValue.Builder.asUInt),
    Type.Kind.UINT32: (int, native.DynamicValue.Builder.asUInt),
    Type.Kind.UINT64: (int, native.DynamicValue.Builder.asUInt),

    Type.Kind.FLOAT32: (float, native.DynamicValue.Builder.asFloat),
    Type.Kind.FLOAT64: (float, native.DynamicValue.Builder.asFloat),

    Type.Kind.TEXT: (str, native.DynamicValue.Builder.asText),
    Type.Kind.DATA: (bytes, native.DynamicValue.Builder.asData),

    Type.Kind.LIST: (DynamicList.Builder, native.DynamicValue.Builder.asList),

    Type.Kind.ENUM: (DynamicEnum, native.DynamicValue.Builder.asEnum),

    Type.Kind.STRUCT: (
        DynamicStruct.Builder, native.DynamicValue.Builder.asStruct),
}


_DYNAMIC_BUILDER_TYPES = frozenset((
    DynamicList.Builder,
    DynamicEnum,
    DynamicStruct.Builder,
))


def _dynamic_value_builder_to_python(type_, value):
    assert isinstance(value, native.DynamicValue.Builder)
    python_type, converter = _DYNAMIC_VALUE_BUILDER_TABLE[type_.kind]
    python_value = converter(value)
    if python_type in _DYNAMIC_BUILDER_TYPES:
        assert type_.schema is not None
        python_value = python_type(type_.schema, python_value)
    assert isinstance(python_value, python_type), (python_value, python_type)
    return python_value
