__all__ = [
    'DynamicListBuilder',
    'DynamicListReader',
    'DynamicStructBuilder',
    'DynamicStructReader',
]

import enum
import functools
import operator

from g1.bases import classes
from g1.bases import collections
from g1.bases.assertions import ASSERT

from . import _capnp
# pylint: disable=c-extension-no-member

from . import bases
from . import schemas


class Base(bases.Base):

    _schema_type = type(None)  # Sub-class must override this.

    def __init__(self, message, schema, raw):
        ASSERT.isinstance(schema, self._schema_type)
        super().__init__(raw)
        # Keep a strong reference to the root message to ensure that it
        # is not garbage-collected before us.
        self._message = message
        self.schema = schema

    __repr__ = classes.make_repr('schema={self.schema} {self!s}')

    def __str__(self):
        raise NotImplementedError


class DynamicListReader(Base):
    """Provide read-only list-like interface for ``DynamicList``."""

    _schema_type = schemas.ListSchema
    _raw_type = _capnp.DynamicList.Reader

    def __init__(self, *args):
        super().__init__(*args)
        # TODO: For now, we do not share to_upper/to_lower among reader
        # and builder objects, even though they might be derived from
        # the same type, because we do not know how to define hash key
        # from types.  (Same below.)
        self.__to_upper = _make_to_upper(self.schema.element_type, True)

    def __str__(self):
        return _capnp.TextCodec().encode(
            _capnp.DynamicValue.Reader.fromDynamicList(self._raw)
        )

    def __len__(self):
        return len(self._raw)

    def __getitem__(self, index):
        if not 0 <= index < len(self):
            raise IndexError(index)
        return self.__to_upper(self._message, self._raw[index])


class DynamicListBuilder(Base):
    """Provide list-like interface for ``DynamicList``."""

    _schema_type = schemas.ListSchema
    _raw_type = _capnp.DynamicList.Builder

    def __init__(self, *args):
        super().__init__(*args)
        self.__to_upper = _make_to_upper(self.schema.element_type, False)
        self.__to_lower = _make_to_lower(self.schema.element_type)

    def __str__(self):
        return _capnp.TextCodec().encode(
            _capnp.DynamicValue.Reader.fromDynamicList(self._raw.asReader())
        )

    def __len__(self):
        return len(self._raw)

    def __getitem__(self, index):
        if not 0 <= index < len(self):
            raise IndexError(index)
        return self.__to_upper(self._message, self._raw[index])

    def __setitem__(self, index, value):
        if not 0 <= index < len(self):
            raise IndexError(index)
        self._raw.set(index, self.__to_lower(value))

    def init(self, index, size=None):
        if not 0 <= index < len(self):
            raise IndexError(index)
        if self.schema.element_type.is_list():
            ASSERT.greater_or_equal(size, 0)
            return DynamicListBuilder(
                self._message,
                self.schema.element_type.as_list(),
                self._raw.init(index, size).asDynamicList(),
            )
        else:
            # Although Builder::init does not support struct type, to
            # make interface consistent between list-of-struct and
            # struct-of-struct, let's return something here rather than
            # erring out.
            ASSERT.true(self.schema.element_type.is_struct())
            return self[index]


class DynamicStructReader(Base):
    """Provide read-only dict-like interface for ``DynamicStruct``."""

    _schema_type = schemas.StructSchema
    _raw_type = _capnp.DynamicStruct.Reader

    def __init__(self, *args):
        super().__init__(*args)
        self.__to_uppers = collections.LoadingDict(
            lambda field: _make_to_upper(field.type, True)
        )

    def __str__(self):
        return _capnp.TextCodec().encode(
            _capnp.DynamicValue.Reader.fromDynamicStruct(self._raw)
        )

    def __contains__(self, name):
        return name in self.schema.fields

    def __iter__(self):
        return iter(self.schema.fields)

    def __getitem__(self, name):
        field = self.schema.fields[name]
        return _struct_getitem(self, field, self.__to_uppers[field])


class DynamicStructBuilder(Base):
    """Provide dict-like interface for ``DynamicStruct``."""

    _schema_type = schemas.StructSchema
    _raw_type = _capnp.DynamicStruct.Builder

    def __init__(self, *args):
        super().__init__(*args)
        self.__to_uppers = collections.LoadingDict(
            lambda field: _make_to_upper(field.type, False)
        )
        self.__to_lowers = collections.LoadingDict(
            lambda field: _make_to_lower(field.type)
        )

    def __str__(self):
        return _capnp.TextCodec().encode(
            _capnp.DynamicValue.Reader.fromDynamicStruct(self._raw.asReader())
        )

    def from_text(self, text):
        _capnp.TextCodec().decode(text, self._raw)

    def as_reader(self):
        return DynamicStructReader(
            self._message, self.schema, self._raw.asReader()
        )

    def __contains__(self, name):
        return name in self.schema.fields

    def __iter__(self):
        return iter(self.schema.fields)

    def __getitem__(self, name):
        field = self.schema.fields[name]
        return _struct_getitem(self, field, self.__to_uppers[field])

    def __setitem__(self, name, value):
        field = self.schema.fields[name]
        self._raw.set(field._raw, self.__to_lowers[field](value))

    def init(self, name, size=None):
        field = self.schema.fields[name]
        # For now let's only accept list and struct, but remember that
        # ``capnp::DynamicStruct::Builder::init`` actually supports more
        # types.
        if field.type.is_list():
            ASSERT.greater_or_equal(size, 0)
            return DynamicListBuilder(
                self._message,
                field.type.as_list(),
                self._raw.init(field._raw, size).asDynamicList(),
            )
        elif field.type.is_struct():
            return DynamicStructBuilder(
                self._message,
                field.type.as_struct(),
                self._raw.init(field._raw).asDynamicStruct(),
            )
        else:
            return ASSERT.unreachable('unexpected item type: {}', field.type)

    def __delitem__(self, name):
        field = self.schema.fields[name]
        self._raw.clear(field._raw)


def _struct_getitem(struct, field, to_upper):
    # By the way, ``NON_NULL`` and ``NON_DEFAULT`` behave the same for
    # pointer types.
    if not struct._raw.has(field._raw, _capnp.HasMode.NON_NULL):
        # Return ``None`` on named union fields.
        if field.proto.is_group():
            return None
        # Return ``None`` on non-pointer fields without a default value.
        if field.proto.is_slot() and not field.proto.slot.had_explicit_default:
            return None
    return to_upper(struct._message, struct._raw.get(field._raw))


_PRIMITIVE_TYPES = {
    which: (
        # type, to_upper, to_lower.
        type_,
        operator.methodcaller('as%s' % name),
        getattr(_capnp.DynamicValue.Reader, 'from%s' % name),
    )
    for which, name, type_ in (
        (_capnp.schema.Type.Which.VOID, 'Void', _capnp.VoidType),
        (_capnp.schema.Type.Which.BOOL, 'Bool', bool),
        (_capnp.schema.Type.Which.INT8, 'Int', int),
        (_capnp.schema.Type.Which.INT16, 'Int', int),
        (_capnp.schema.Type.Which.INT32, 'Int', int),
        (_capnp.schema.Type.Which.INT64, 'Int', int),
        (_capnp.schema.Type.Which.UINT8, 'Uint', int),
        (_capnp.schema.Type.Which.UINT16, 'Uint', int),
        (_capnp.schema.Type.Which.UINT32, 'Uint', int),
        (_capnp.schema.Type.Which.UINT64, 'Uint', int),
        (_capnp.schema.Type.Which.FLOAT32, 'Float', float),
        (_capnp.schema.Type.Which.FLOAT64, 'Float', float),
    )
}


def _make_to_upper(item_type, is_reader):

    # Handle non-pointer types first.

    result = _PRIMITIVE_TYPES.get(item_type.which)
    if result:
        return functools.partial(_primitive_to_upper, result[1])

    if item_type.is_enum():
        return _enum_to_upper

    # Handle pointer types.

    if item_type.is_text():
        return _text_to_upper

    if item_type.is_data():
        return _data_to_upper

    if item_type.is_list():
        return functools.partial(
            _list_to_upper,
            # TODO: Sadly, this will break users who subclass
            # DynamicListReader or DynamicListBuilder (same below) as we
            # hard code types here.
            DynamicListReader if is_reader else DynamicListBuilder,
            item_type.as_list(),
        )

    if item_type.is_struct():
        return functools.partial(
            _struct_to_upper,
            DynamicStructReader if is_reader else DynamicStructBuilder,
            item_type.as_struct(),
        )

    if item_type.is_interface():
        raise NotImplementedError('do not support interface for now')

    if item_type.is_any_pointer():
        raise NotImplementedError('do not support any-pointer for now')

    return ASSERT.unreachable('unexpected item type: {}', item_type)


def _primitive_to_upper(to_upper, message, value):
    del message  # Unused.
    return to_upper(value)


def _enum_to_upper(message, value):
    del message  # Unused.
    # Simply return the enum value and do not convert it to Python enum
    # type; implement the conversion at higher level.
    return value.asDynamicEnum().getRaw()


def _text_to_upper(message, value):
    del message  # Unused.
    # Should I return a memory view instead?
    return str(value.asText(), 'utf-8')


def _data_to_upper(message, value):
    del message  # Unused.
    return value.asData()


def _list_to_upper(list_type, schema, message, value):
    return list_type(message, schema, value.asDynamicList())


def _struct_to_upper(struct_type, schema, message, value):
    return struct_type(message, schema, value.asDynamicStruct())


def _make_to_lower(item_type):

    # Handle non-pointer types first.

    result = _PRIMITIVE_TYPES.get(item_type.which)
    if result:
        return functools.partial(_primitive_to_lower, result[0], result[2])

    if item_type.is_enum():
        return functools.partial(_enum_to_lower, item_type.as_enum())

    # Handle pointer types.

    if item_type.is_text():
        return _text_to_lower

    if item_type.is_data():
        return _data_to_lower

    if item_type.is_list():
        return _list_to_lower

    if item_type.is_struct():
        return _struct_to_lower

    if item_type.is_interface():
        raise NotImplementedError('do not support interface for now')

    if item_type.is_any_pointer():
        raise NotImplementedError('do not support any-pointer for now')

    return ASSERT.unreachable('unexpected item type: {}', item_type)


def _primitive_to_lower(type_, to_lower, value):
    ASSERT.isinstance(value, type_)
    return to_lower(value)


def _enum_to_lower(schema, value):
    if isinstance(value, enum.Enum):
        value = value.value
    ASSERT.isinstance(value, int)
    return _capnp.DynamicValue.Reader.fromDynamicEnum(
        _capnp.DynamicEnum(schema._raw, value)
    )


def _text_to_lower(value):
    ASSERT.isinstance(value, str)
    return _capnp.DynamicValue.Reader.fromText(value)


def _data_to_lower(value):
    ASSERT.isinstance(value, (bytes, memoryview))
    return _capnp.DynamicValue.Reader.fromData(value)


def _list_to_lower(value):
    if isinstance(value, DynamicListReader):
        reader = value._raw
    else:
        ASSERT.isinstance(value, DynamicListBuilder)
        reader = value._raw.asReader()
    return _capnp.DynamicValue.Reader.fromDynamicList(reader)


def _struct_to_lower(value):
    if isinstance(value, DynamicStructReader):
        reader = value._raw
    else:
        ASSERT.isinstance(value, DynamicStructBuilder)
        reader = value._raw.asReader()
    return _capnp.DynamicValue.Reader.fromDynamicStruct(reader)
