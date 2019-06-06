__all__ = [
    'DynamicListBuilder',
    'DynamicListReader',
    'DynamicStructBuilder',
    'DynamicStructReader',
]

import enum

from g1.bases import classes
from g1.bases.assertions import ASSERT

from . import _capnp
# pylint: disable=c-extension-no-member

from . import bases
from . import schemas


class Base(bases.Base):

    _schema_type = type(None)  # Sub-class must override this.

    def __init__(self, schema, raw):
        ASSERT.isinstance(schema, self._schema_type)
        super().__init__(raw)
        self.schema = schema

    __repr__ = classes.make_repr('schema={self.schema}')


class DynamicListReader(Base):
    """Provide read-only list-like interface for ``DynamicList``."""

    _is_reader_type = True
    _schema_type = schemas.ListSchema
    _raw_type = _capnp.DynamicList.Reader

    def __len__(self):
        return len(self._raw)

    def __getitem__(self, index):
        if not 0 <= index < len(self):
            raise IndexError(index)
        return _getitem(
            self.__class__,
            self.schema.element_type,
            self._raw.__getitem__,
            index,
        )


class DynamicListBuilder(Base):
    """Provide list-like interface for ``DynamicList``."""

    _is_reader_type = False
    _schema_type = schemas.ListSchema
    _raw_type = _capnp.DynamicList.Builder

    def __len__(self):
        return len(self._raw)

    def __getitem__(self, index):
        if not 0 <= index < len(self):
            raise IndexError(index)
        return _getitem(
            self.__class__,
            self.schema.element_type,
            self._raw.__getitem__,
            index,
        )

    def __setitem__(self, index, value):
        if not 0 <= index < len(self):
            raise IndexError(index)
        _setitem(self.schema.element_type, self._raw.set, index, value)

    def init(self, index, size):
        if not 0 <= index < len(self):
            raise IndexError(index)
        # For now let's only accept list, but remember that
        # ``capnp::DynamicList::Builder::init`` actually supports more
        # types.
        if self.schema.element_type.is_list():
            ASSERT.greater_or_equal(size, 0)
            return DynamicListBuilder(
                self.schema.element_type.as_list(),
                self._raw.init(index, size).asDynamicList(),
            )
        else:
            return ASSERT.unreachable(
                'unexpected item type: {}', self.schema.element_type
            )


class DynamicStructReader(Base):
    """Provide read-only dict-like interface for ``DynamicStruct``."""

    _is_reader_type = True
    _schema_type = schemas.StructSchema
    _raw_type = _capnp.DynamicStruct.Reader

    def __contains__(self, name):
        return name in self.schema.fields

    def __iter__(self):
        return iter(self.schema.fields)

    def __getitem__(self, name):
        field = self.schema.fields[name]
        return _struct_getitem(self, field)


class DynamicStructBuilder(Base):
    """Provide dict-like interface for ``DynamicStruct``."""

    _is_reader_type = False
    _schema_type = schemas.StructSchema
    _raw_type = _capnp.DynamicStruct.Builder

    def __contains__(self, name):
        return name in self.schema.fields

    def __iter__(self):
        return iter(self.schema.fields)

    def __getitem__(self, name):
        field = self.schema.fields[name]
        return _struct_getitem(self, field)

    def __setitem__(self, name, value):
        field = self.schema.fields[name]
        _setitem(field.type, self._raw.set, field._raw, value)

    def init(self, name, size=None):
        field = self.schema.fields[name]
        # For now let's only accept list and struct, but remember that
        # ``capnp::DynamicStruct::Builder::init`` actually supports more
        # types.
        if field.type.is_list():
            ASSERT.greater_or_equal(size, 0)
            return DynamicListBuilder(
                field.type.as_list(),
                self._raw.init(field._raw, size).asDynamicList(),
            )
        elif field.type.is_struct():
            return DynamicStructBuilder(
                field.type.as_struct(),
                self._raw.init(field._raw).asDynamicStruct(),
            )
        else:
            return ASSERT.unreachable('unexpected item type: {}', field.type)

    def __delitem__(self, name):
        field = self.schema.fields[name]
        self._raw.clear(field._raw)


def _struct_getitem(struct, field):
    # By the way, ``NON_NULL`` and ``NON_DEFAULT`` behave the same for
    # pointer types.
    if not struct._raw.has(field._raw, _capnp.HasMode.NON_NULL):
        # Return ``None`` on union member that is not selected.
        if struct.schema.proto.struct.is_group:
            return None
        # Return ``None`` on null pointer items without a default value.
        if field.proto.is_slot() and not field.proto.slot.had_explicit_default:
            return None
    return _getitem(struct.__class__, field.type, struct._raw.get, field._raw)


_PRIMITIVE_TYPES = {
    _capnp.schema.Type.Which.VOID: ('Void', _capnp.VoidType),
    _capnp.schema.Type.Which.BOOL: ('Bool', bool),
    _capnp.schema.Type.Which.INT8: ('Int', int),
    _capnp.schema.Type.Which.INT16: ('Int', int),
    _capnp.schema.Type.Which.INT32: ('Int', int),
    _capnp.schema.Type.Which.INT64: ('Int', int),
    _capnp.schema.Type.Which.UINT8: ('Uint', int),
    _capnp.schema.Type.Which.UINT16: ('Uint', int),
    _capnp.schema.Type.Which.UINT32: ('Uint', int),
    _capnp.schema.Type.Which.UINT64: ('Uint', int),
    _capnp.schema.Type.Which.FLOAT32: ('Float', float),
    _capnp.schema.Type.Which.FLOAT64: ('Float', float),
}


def _getitem(collection_type, item_type, getitem, key):

    item_value = getitem(key)

    # Handle non-pointer types first.

    name, _ = _PRIMITIVE_TYPES.get(item_type.which, (None, None))
    if name:
        return getattr(item_value, 'as%s' % name)()

    if item_type.is_enum():
        # Simply return the enum value and do not convert it to Python
        # enum type; implement the conversion at higher level.
        return item_value.asDynamicEnum().getRaw()

    # Handle pointer types.

    if item_type.is_text():
        # Should I return a memory view instead?
        return str(item_value.asText(), 'utf8')

    if item_type.is_data():
        return item_value.asData()

    if item_type.is_list():
        if collection_type._is_reader_type:
            list_type = DynamicListReader
        else:
            list_type = DynamicListBuilder
        return list_type(
            item_type.as_list(),
            item_value.asDynamicList(),
        )

    if item_type.is_struct():
        if collection_type._is_reader_type:
            struct_type = DynamicStructReader
        else:
            struct_type = DynamicStructBuilder
        return struct_type(
            item_type.as_struct(),
            item_value.asDynamicStruct(),
        )

    if item_type.is_interface():
        raise NotImplementedError('do not support interface for now')

    if item_type.is_any_pointer():
        raise NotImplementedError('do not support any-pointer for now')

    return ASSERT.unreachable('unexpected item type: {}', item_type)


def _setitem(item_type, setitem, key, value):

    # Handle non-pointer types first.

    name, type_ = _PRIMITIVE_TYPES.get(item_type.which, (None, None))
    if name:
        ASSERT.isinstance(value, type_)
        dvalue = getattr(_capnp.DynamicValue.Reader, 'from%s' % name)(value)
        setitem(key, dvalue)
        return

    if item_type.is_enum():
        if isinstance(value, enum.Enum):
            value = value.value
        ASSERT.isinstance(value, int)
        dvalue = _capnp.DynamicValue.Reader.fromDynamicEnum(
            _capnp.DynamicEnum(item_type.as_enum()._raw, value)
        )
        setitem(key, dvalue)
        return

    # Handle pointer types.

    if item_type.is_text():
        ASSERT.isinstance(value, str)
        setitem(key, _capnp.DynamicValue.Reader.fromText(value))
        return

    if item_type.is_data():
        ASSERT.isinstance(value, (bytes, memoryview))
        setitem(key, _capnp.DynamicValue.Reader.fromData(value))
        return

    if item_type.is_list():
        if isinstance(value, DynamicListReader):
            reader = value._raw
        else:
            ASSERT.isinstance(value, DynamicListBuilder)
            reader = value._raw.asReader()
        setitem(key, _capnp.DynamicValue.Reader.fromDynamicList(reader))
        return

    if item_type.is_struct():
        if isinstance(value, DynamicStructReader):
            reader = value._raw
        else:
            ASSERT.isinstance(value, DynamicStructBuilder)
            reader = value._raw.asReader()
        setitem(key, _capnp.DynamicValue.Reader.fromDynamicStruct(reader))
        return

    if item_type.is_interface():
        raise NotImplementedError('do not support interface for now')

    if item_type.is_any_pointer():
        raise NotImplementedError('do not support any-pointer for now')

    ASSERT.unreachable('unexpected item type: {}', item_type)
