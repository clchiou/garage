__all__ = [
    'DynamicObject',
    'DynamicListAdapter',
    'register_converter',
]

import collections

from . import bases
from .schemas import Type
from .dynamics import DynamicEnum
from .dynamics import DynamicList
from .dynamics import DynamicStruct


_CONVERTER_TABLE = {}


def register_converter(type_, converter):
    if type_ in _CONVERTER_TABLE:
        raise ValueError('cannot override converter: type=%r' % type_)
    _CONVERTER_TABLE[type_] = converter


def _identity_converter(value):
    return value


def _convert(value):
    return _CONVERTER_TABLE.get(type(value), _identity_converter)(value)


register_converter(DynamicEnum, lambda e: e.get())


class DynamicObjectMeta(type):

    DYNAMIC_OBJECT_CLASS = {}

    @classmethod
    def convert_struct(mcs, struct):
        cls = mcs.DYNAMIC_OBJECT_CLASS.get(struct.schema, DynamicObject)
        return cls(struct)

    def __new__(mcs, class_name, base_classes, namespace, schema=None):
        if schema in mcs.DYNAMIC_OBJECT_CLASS:
            raise ValueError('cannot override: %r' % schema)
        cls = super().__new__(mcs, class_name, base_classes, namespace)
        if schema is not None:
            mcs.DYNAMIC_OBJECT_CLASS[schema] = cls
        return cls

    def __init__(cls, name, base_classes, namespace, **_):
        super().__init__(name, base_classes, namespace)


register_converter(DynamicStruct, DynamicObjectMeta.convert_struct)
register_converter(DynamicStruct.Builder, DynamicObjectMeta.convert_struct)


class DynamicObject(metaclass=DynamicObjectMeta):
    """Let you access DynamicStruct like a regular read-only object.

    NOTE: Cap'n Proto's data model is quite different from the normal
    Python object field access semantics - at least for now I can't
    reconcile the differences of the two sides; as a result, this class
    is quite awkward to use at the moment.
    """

    __annotations__ = {}

    def __init__(self, struct):
        assert isinstance(struct, (DynamicStruct, DynamicStruct.Builder))
        super().__setattr__('_struct', struct)

    def _init(self, name, size=None):
        camel_case = bases.snake_to_lower_camel(name)
        value = _convert(self._struct.init(camel_case, size))
        value = self.__annotations__.get(name, _identity_converter)(value)
        return value

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
        value = self.__annotations__.get(name, _identity_converter)(value)

        return value

    def __setattr__(self, name, value):

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
        camel_case = bases.snake_to_lower_camel(name)
        try:
            self._struct.pop(name)
        except KeyError:
            msg = '%s cannot delete %r' % (self._struct.schema, camel_case)
            raise AttributeError(msg) from None

    def __str__(self):
        return str(self._struct)

    __repr__ = bases.repr_object


class DynamicListAdapter(collections.MutableSequence):

    def __init__(self, list_):
        assert isinstance(list_, (DynamicList, DynamicList.Builder))
        self._list = list_

    def __len__(self):
        return len(self._list)

    def __iter__(self):
        yield from map(_convert, self._list)

    def _init(self, index, size=None):
        return _convert(self._list.init(index, size))

    def __getitem__(self, index):
        return _convert(self._list[index])

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


register_converter(DynamicList, DynamicListAdapter)
register_converter(DynamicList.Builder, DynamicListAdapter)


def _setter_helper(type_, target, key, value, get_obj):

    if type_.kind is Type.Kind.VOID or type_.kind.is_scalar:
        target[key] = value

    elif type_.kind is Type.Kind.LIST:
        target.init(key, len(value))
        obj = get_obj()
        for index, element in enumerate(value):
            obj[index] = element

    elif type_.kind is Type.Kind.STRUCT:
        if not isinstance(value, collections.Mapping):
            raise ValueError('cannot assign from: %s %s %r' %
                             (type_, key, value))
        target.init(key)
        obj = get_obj()
        for k, v in value.items():
            setattr(obj, k, v)

    else:
        raise AssertionError('cannot assign to: %s %s' % (type_, key))
