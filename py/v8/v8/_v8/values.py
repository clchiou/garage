__all__ = [
    'Array',
    'Object',
    'Script',
    'String',
    'Value',
]

from garage import asserts

from .base import C, ObjectBase
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
            C.v8_array_cast_from(not_null(value.value)),
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
            C.v8_map_cast_from(not_null(value.value)),
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
    )


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
        ctor=C.v8_string_new_from_utf8,
        dtor=C.v8_string_delete,
    )

    @classmethod
    def from_str(cls, str_, isolate):
        return cls(isolate.isolate, str_.encode('utf-8'))


class Value(ObjectBase):

    _spec = ObjectBase.Spec(
        name='value',
        ctor=lambda value: value,
        dtor=C.v8_value_delete,
    )

    value = None

    def is_array(self):
        return bool(C.v8_value_is_array(not_null(self.value)))

    def is_map(self):
        return bool(C.v8_value_is_map(not_null(self.value)))

    def is_string(self):
        return bool(C.v8_value_is_string(not_null(self.value)))

    def is_number(self):
        return bool(C.v8_value_is_number(not_null(self.value)))

    def is_int32(self):
        return bool(C.v8_value_is_int32(not_null(self.value)))

    def is_uint32(self):
        return bool(C.v8_value_is_uint32(not_null(self.value)))

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
        return C.v8_number_cast_from(not_null(self.value))

    def _as_str(self):
        utf8_value = not_null(C.v8_utf8_value_new(not_null(self.value)))
        try:
            return not_null(C.v8_utf8_value_cstr(utf8_value)).decode('utf-8')
        finally:
            C.v8_utf8_value_delete(utf8_value)
