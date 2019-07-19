__all__ = [
    'select',
]

import dataclasses

from g1.bases import typings
from g1.bases.assertions import ASSERT

NoneType = type(None)


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
