__all__ = [
    'DynamicObject',
    'DynamicListAdapter',
    'register_converter',
    'register_serializer',
]

import collections
import enum

from . import bases
from .schemas import Type
from .dynamics import DynamicEnum
from .dynamics import DynamicList
from .dynamics import DynamicStruct


_CONVERTER_TABLE = {}
_SERIALIZER_TABLE = collections.OrderedDict()


def register_converter(type_, converter):
    """Register a converter for the given type.

    A converter transforms capnp-domain value into Python-domain.
    """
    if type_ in _CONVERTER_TABLE:
        raise ValueError('cannot override converter: type=%r' % type_)
    _CONVERTER_TABLE[type_] = converter


def register_serializer(type_, serializer):
    """Register a serializer for the given type and all its sub-types.

    A serializer transforms Python value into another that is suitable
    for JSON or YAML serialization.

    Note that serializer is matched with all sub-types because it is
    common that you sub-class a Python type (which is not so for capnp-
    domain types).
    """
    if type_ in _SERIALIZER_TABLE:
        raise ValueError('cannot override serializer: type=%r' % type_)
    _SERIALIZER_TABLE[type_] = serializer


def _identity_func(value):
    return value


def _convert(value):
    return _CONVERTER_TABLE.get(type(value), _identity_func)(value)


def _serialize(value):
    for type_, serializer in _SERIALIZER_TABLE.items():
        if isinstance(value, type_):
            value = serializer(value)
            break
    return value


def _set_root(node, leaf):
    """Add a reference from leaf to root.

    This should prevent root node from being garbage collected while
    leaf is still alive (downside is that it may retain more memory).
    """
    if isinstance(leaf, (DynamicObject, DynamicListAdapter)):
        assert leaf._root is None
        leaf._root = node if node._root is None else node._root
    return leaf


register_converter(DynamicEnum, lambda e: e.get())
register_serializer(enum.Enum, lambda e: e.value)


class DynamicObjectMeta(type):

    DYNAMIC_OBJECT_CLASS = {}

    @classmethod
    def convert_struct(mcs, struct):
        cls = mcs.DYNAMIC_OBJECT_CLASS.get(struct.schema, DynamicObject)
        return cls(struct)

    def __new__(mcs, class_name, base_classes, namespace, schema=None):
        if schema in mcs.DYNAMIC_OBJECT_CLASS:
            raise ValueError('cannot override: %r' % schema)
        if schema is not None:
            namespace['_schema'] = schema
        cls = super().__new__(mcs, class_name, base_classes, namespace)
        if schema is not None:
            mcs.DYNAMIC_OBJECT_CLASS[schema] = cls
        return cls

    def __init__(cls, name, base_classes, namespace, **_):
        super().__init__(name, base_classes, namespace)


class DynamicObject(metaclass=DynamicObjectMeta):
    """Let you access DynamicStruct like a regular object.

    NOTE: Cap'n Proto's data model is quite different from the normal
    Python object semantics - at least for now I can't reconcile the
    differences of the two sides; as a result, this class is quite
    awkward to use at the moment.
    """

    __annotations__ = {}

    _schema = None

    @classmethod
    def _make(cls, message, schema=None):
        """Make a DynamicObject from message and default schema.

        This will "own" the message object, and thus you should neither
        open the message before calling this, nor close the message
        afterwards.
        """
        if schema is None:
            schema = cls._schema
        assert schema is not None
        message.open()
        try:
            obj = cls(message.get_root(schema))
            obj._message = message
            return obj
        except:
            message.close()
            raise

    def __init__(self, struct):
        assert isinstance(struct, (DynamicStruct, DynamicStruct.Builder))
        self._message = None
        self._struct = struct
        self._root = None

    def __del__(self):
        # Release C++ resources, just to be safe.
        self._close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._close()

    def _close(self):
        if self._message is not None:
            self._struct, self._message, message = None, None, self._message
            message.close()

    def _as_reader(self):
        return _set_root(self, self.__class__(self._struct.as_reader()))

    def _items(self):
        for camel_case in self._struct.keys():
            name = bases.camel_to_lower_snake(camel_case)
            # Use getattr() so that converter may participate.
            value = getattr(self, name)
            yield name, value

    def _serialize_asdict(self):
        return collections.OrderedDict(
            (name, _serialize(value))
            for name, value in self._items()
        )

    def _init(self, name, size=None):
        camel_case = bases.snake_to_lower_camel(name)
        value = _convert(self._struct.init(camel_case, size))
        value = self.__annotations__.get(name, _identity_func)(value)
        return _set_root(self, value)

    def __getattr__(self, name):

        # Translate name.
        camel_case = bases.snake_to_lower_camel(name)

        try:
            field = self._struct.schema[camel_case]
        except KeyError:
            msg = '%s has no field %r' % (self._struct.schema, camel_case)
            raise AttributeError(msg) from None

        # Retrieve the attribute.
        try:
            value = self._struct[camel_case]
        except KeyError:
            # Return default value for this attribute.
            if field.type.kind is Type.Kind.LIST:
                return ()
            else:
                return None

        # Apply registered converter.
        value = _convert(value)

        # Apply per-struct converter.
        value = self.__annotations__.get(name, _identity_func)(value)

        return _set_root(self, value)

    def __setattr__(self, name, value):

        # Special case for attribute name started with '_'.
        if name.startswith('_'):
            super().__setattr__(name, value)
            return

        camel_case = bases.snake_to_lower_camel(name)

        try:
            field = self._struct.schema[camel_case]
        except KeyError:
            msg = '%s has no field %r' % (self._struct.schema, camel_case)
            raise AttributeError(msg) from None

        _setter_helper(
            field.type,
            self._struct,
            camel_case,
            value,
            lambda: getattr(self, name),
        )

    def __delattr__(self, name):

        # Special case for attribute name started with '_'.
        if name.startswith('_'):
            super().__delattr__(name)
            return

        camel_case = bases.snake_to_lower_camel(name)
        try:
            self._struct.pop(camel_case)
        except KeyError:
            msg = '%s cannot delete %r' % (self._struct.schema, camel_case)
            raise AttributeError(msg) from None

    def __str__(self):
        return str(self._struct)

    __repr__ = bases.repr_object

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return self._struct == other._struct

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self._struct)


register_converter(DynamicStruct, DynamicObjectMeta.convert_struct)
register_converter(DynamicStruct.Builder, DynamicObjectMeta.convert_struct)
register_serializer(DynamicObject, DynamicObject._serialize_asdict)


class DynamicListAdapter(collections.MutableSequence):

    def __init__(self, list_):
        assert isinstance(list_, (DynamicList, DynamicList.Builder))
        self._list = list_
        self._root = None

    def _serialize_aslist(self):
        return list(map(_serialize, self))

    def __len__(self):
        return len(self._list)

    def __iter__(self):
        for obj in map(_convert, self._list):
            yield _set_root(self, obj)

    def _init(self, index, size=None):
        obj = _convert(self._list.init(index, size))
        return _set_root(self, obj)

    def __getitem__(self, index):
        obj = _convert(self._list[index])
        return _set_root(self, obj)

    def __setitem__(self, index, value):
        _setter_helper(
            self._list.schema.element_type,
            self._list,
            index,
            value,
            lambda: self[index],
        )

    def __delitem__(self, index):
        raise IndexError('do not support __delitem__')

    def insert(self, index, value):
        raise IndexError('do not support insert')

    def __str__(self):
        return str(self._list)

    __repr__ = bases.repr_object

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return self._list == other._list

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self._list)


register_converter(DynamicList, DynamicListAdapter)
register_converter(DynamicList.Builder, DynamicListAdapter)
register_serializer(DynamicListAdapter, DynamicListAdapter._serialize_aslist)


def _setter_helper(type_, target, key, value, get_obj):

    if type_.kind is Type.Kind.VOID:
        target[key] = value

    elif type_.kind.is_scalar:
        if value is None:
            if key in target:
                del target[key]
        else:
            target[key] = value

    elif type_.kind is Type.Kind.LIST:
        if value:
            target.init(key, len(value))
            obj = get_obj()
            for index, element in enumerate(value):
                obj[index] = element
        else:
            if key in target:
                del target[key]

    elif type_.kind is Type.Kind.STRUCT:

        if (isinstance(value, DynamicObject) and
                type_.schema is value._struct.schema):
            target.init(key)
            obj = get_obj()
            obj._struct.copy_from(value._struct)

        elif isinstance(value, collections.Mapping):
            target.init(key)
            obj = get_obj()
            for k, v in value.items():
                setattr(obj, k, v)

        elif not value:
            if key in target:
                del target[key]

        else:
            raise ValueError(
                'cannot assign from: %s %s %r' % (type_, key, value))

    else:
        raise AssertionError('cannot assign to: %s %s' % (type_, key))
