"""Extensions of standard library's dataclasses."""

__all__ = [
    'fromdict',
]

import collections.abc
import dataclasses

from . import typings
from .assertions import ASSERT


def fromdict(dataclass, data):
    """Construct a dataclass object from a dict.

    This is the inverse of ``dataclasses.asdict``.  Note that this
    ignores dict entries that do not correspond to any dataclass field.

    This only handles a small number of "structure" schema definitions,
    namely, typing.List, typing.Tuple, typing.Optional, and
    typing.Mapping.
    """

    def convert(type_, value):
        result = value

        if typings.is_recursive_type(type_):
            if type_.__origin__ is list:
                element_type = type_.__args__[0]
                result = [convert(element_type, element) for element in value]

            elif type_.__origin__ is tuple:
                ASSERT.equal(len(value), len(type_.__args__))
                result = tuple(
                    convert(element_type, element)
                    for element_type, element in zip(type_.__args__, value)
                )

            elif typings.is_union_type(type_):
                optional_type_ = typings.match_optional_type(type_)
                if optional_type_ and value is not None:
                    result = convert(optional_type_, value)

            elif type_.__origin__ in (
                collections.abc.Mapping,
                collections.abc.MutableMapping,
            ):
                ASSERT.equal(len(type_.__args__), 2)
                result = {
                    convert(type_.__args__[0], k):
                    convert(type_.__args__[1], v)
                    for k, v in value.items()
                }

        elif dataclasses.is_dataclass(type_):
            result = fromdict(type_, value)

        return result
    return dataclass(
        **{
            field.name: convert(field.type, data[field.name])
            for field in dataclasses.fields(dataclass)
            if field.name in data
        }
    )
