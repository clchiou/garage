__all__ = [
    'Array',
    'Object',
    'ObjectDictProxy',
    'Script',
    'String',
    'Value',
]

import ctypes

from garage import asserts

from .base import C, ObjectBase
from .loader import BOOL
from .utils import not_null


class Array(ObjectBase):

    _spec = ObjectBase.Spec(
        name='array',
        extra=['context'],
        ctor=lambda array, context: (array, context),
        dtor=C.v8_array_delete,
    )

    array = None
    context = None

    def __len__(self):
        return C.v8_array_length(not_null(self.array))

    def __iter__(self):
        for i in range(len(self)):
            yield self._get_unchecked(i)

    def __getitem__(self, index):
        asserts.precond(0 <= index < len(self))
        return self._get_unchecked(index)

    def _get_unchecked(self, index):
        return Value(C.v8_array_get(
            not_null(self.array),
            not_null(self.context.context),
            index,
        ))


class Object(ObjectBase):

    _spec = ObjectBase.Spec(
        name='object',
        ctor=lambda object: object,
        dtor=C.v8_object_delete,
    )


class ObjectDictProxy:

    def __init__(self, context, object):
        self.context = context
        self.object = object

    def __contains__(self, key):
        asserts.precond(isinstance(key, Value))
        has = BOOL(0)
        asserts.postcond(C.v8_object_has(
            not_null(self.object.object),
            not_null(self.context.context),
            not_null(key.value),
            ctypes.byref(has),
        ))
        return has.value != 0

    def __iter__(self):
        names = Array(
            C.v8_object_get_property_names(
                not_null(self.object.object),
                not_null(self.context.context),
            ),
            self.context,
        )
        try:
            yield from names
        finally:
            names.close()

    def __getitem__(self, key):
        asserts.precond(isinstance(key, Value))
        value = C.v8_object_get(
            not_null(self.object.object),
            not_null(self.context.context),
            not_null(key.value),
        )
        if value is None:
            raise KeyError(key)
        return Value(value)


class Script(ObjectBase):

    _spec = ObjectBase.Spec(
        name='script',
        ctor=lambda script: script,
        dtor=C.v8_script_delete,
    )

    script = None

    @classmethod
    def compile(cls, context, source):
        asserts.precond(isinstance(source, String))
        return cls(C.v8_script_compile(
            not_null(context.context),
            not_null(source.string),
        ))

    def run(self, context):
        return Value(C.v8_script_run(
            not_null(self.script),
            not_null(context.context),
        ))


class String(ObjectBase):

    _spec = ObjectBase.Spec(
        name='string',
        ctor=C.v8_string_new_from_utf8,
        dtor=C.v8_string_delete,
    )


class Value(ObjectBase):

    _spec = ObjectBase.Spec(
        name='value',
        ctor=lambda value: value,
        dtor=C.v8_value_delete,
    )

    value = None

    def is_string(self):
        return bool(C.v8_value_is_string(not_null(self.value)))

    def __str__(self):
        utf8_value = not_null(C.v8_utf8_value_new(not_null(self.value)))
        try:
            return not_null(C.v8_utf8_value_cstr(utf8_value)).decode('utf-8')
        finally:
            C.v8_utf8_value_delete(utf8_value)
