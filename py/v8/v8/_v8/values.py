__all__ = [
    'Array',
    'Object',
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
        ctor=lambda array: array,
        dtor=C.v8_array_delete,
        fields=['context'],
    )

    array = None
    context = None

    @classmethod
    def from_value(cls, value, context):
        asserts.precond(value.is_array())
        return cls(
            C.v8_array_from_value(not_null(value.value)),
            context=context,
        )

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


class Map(ObjectBase):

    _spec = ObjectBase.Spec(
        name='map',
        ctor=lambda map: map,
        dtor=C.v8_map_delete,
        fields=['context'],
    )

    map = None
    context = None

    @classmethod
    def from_value(cls, value, context):
        asserts.precond(value.is_map())
        return cls(
            C.v8_map_from_value(not_null(value.value)),
            context=context,
        )

    def as_array(self):
        return Array(
            C.v8_map_as_array(not_null(self.map)),
            context=self.context,
        )


class Object(ObjectBase):

    _spec = ObjectBase.Spec(
        name='object',
        ctor=lambda object: object,
        dtor=C.v8_object_delete,
        fields=['context'],
    )

    object = None
    context = None

    @classmethod
    def from_value(cls, value, context):
        asserts.precond(value.is_object())
        return cls(
            C.v8_object_from_value(not_null(value.value)),
            context=context,
        )

    def get_property_names(self):
        return Array(
            C.v8_object_get_property_names(
                not_null(self.object),
                not_null(self.context.context),
            ),
            context=self.context,
        )

    def has_prop(self, name):
        has = BOOL(0)
        asserts.postcond(C.v8_object_has(
            not_null(self.object),
            not_null(self.context.context),
            not_null(name.value),
            ctypes.byref(has),
        ))
        return has.value != 0

    def get_prop(self, name):
        value = Value(C.v8_object_get(
            not_null(self.object),
            not_null(self.context.context),
            not_null(name.value),
        ))
        if value.is_undefined():
            value.close()
            raise AttributeError
        return value


class Script(ObjectBase):

    _spec = ObjectBase.Spec(
        name='script',
        ctor=lambda script: script,
        dtor=C.v8_script_delete,
        fields=['context'],
    )

    script = None
    context = None

    @classmethod
    def compile(cls, context, source):
        return cls(
            C.v8_script_compile(
                not_null(context.context),
                not_null(source.string),
            ),
            context=context,
        )

    def run(self):
        return Value(C.v8_script_run(
            not_null(self.script),
            not_null(self.context.context),
        ))


class String(ObjectBase):

    _spec = ObjectBase.Spec(
        name='string',
        ctor=C.v8_string_from_cstr,
        dtor=C.v8_string_delete,
    )

    @classmethod
    def from_str(cls, str_, isolate):
        return cls(isolate.isolate, str_.encode('utf-8'))


def add_predicates(namespace):

    def make_predicate(name):
        c_predicate = getattr(C, 'v8_value_is_%s' % name)
        def predicate(self):
            return bool(c_predicate(not_null(self.value)))
        return predicate

    names = (
        'undefined',
        'null',
        'true',
        'false',

        'object',
        'array',
        'array_buffer',
        'array_buffer_view',
        'shared_array_buffer',
        'date',
        'function',
        'map',
        'promise',
        'regexp',
        'set',
        'string',
        'boolean_object',
        'number_object',
        'string_object',
        'symbol_object',

        'number',
        'int32',
        'uint32',
    )

    for name in names:
        predicate_name = 'is_%s' % name
        predicate = make_predicate(name)
        predicate.__name__ = predicate_name
        namespace[predicate_name] = predicate


class Value(ObjectBase):

    _spec = ObjectBase.Spec(
        name='value',
        ctor=lambda value: value,
        dtor=C.v8_value_delete,
    )

    value = None

    @classmethod
    def from_string(cls, string):
        return cls(C.v8_value_from_string(not_null(string.string)))

    add_predicates(locals())

    def as_object(self, context):
        return Object.from_value(self, context)

    def as_array(self, context):
        return Array.from_value(self, context)

    def as_map(self, context):
        return Map.from_value(self, context)

    def as_str(self):
        asserts.precond(self.is_string())
        return self._as_str()

    def as_float(self):
        asserts.precond(self.is_number())
        return self._as_number()

    def as_int(self):
        asserts.precond(self.is_int32() or self.is_uint32())
        return int(self._as_number())

    def __str__(self):
        return self._as_str()

    def _as_number(self):
        return C.v8_number_from_value(not_null(self.value))

    def _as_str(self):
        utf8_value = not_null(C.v8_utf8_value_new(not_null(self.value)))
        try:
            return not_null(C.v8_utf8_value_cstr(utf8_value)).decode('utf-8')
        finally:
            C.v8_utf8_value_delete(utf8_value)
