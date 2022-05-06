__all__ = [
    'get_declared_error_types',
    'select',
]

import dataclasses

from g1.bases import typings
from g1.bases.assertions import ASSERT

NoneType = type(None)


def get_declared_error_types(response_type):
    # When there is only one error type, reqrep.make_annotations
    # would not generate Optional[T].
    fields = dataclasses.fields(response_type.Error)
    if len(fields) == 1:
        return {ASSERT.issubclass(fields[0].type, Exception): fields[0].name}
    else:
        return {
            ASSERT(
                typings.is_recursive_type(field.type)
                and typings.is_union_type(field.type)
                and typings.match_optional_type(field.type),
                'expect typing.Optional[T]: {!r}',
                field,
            ): field.name
            for field in fields
        }


def select(obj):
    none_field = None
    for field in dataclasses.fields(obj):
        value = getattr(obj, field.name)
        if value is not None:
            return field.name, value
        elif typings.type_is_subclass(field.type, NoneType):
            none_field = field.name
    if none_field:
        return none_field, None
    return ASSERT.unreachable('expect one non-None field: {!r}', obj)
