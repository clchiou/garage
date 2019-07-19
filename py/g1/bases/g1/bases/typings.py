"""Utilities for matching recursive types.

NOTE: Some of the utility functions depends on the internal parts of the
``typing`` module; we should figure out a way to remove such hacks.
"""

__all__ = [
    'is_recursive_type',
    'is_union_type',
    'match_optional_type',
]

import typing

NoneType = type(None)


def is_recursive_type(type_):
    return isinstance(type_, typing._GenericAlias)


def is_union_type(type_):
    # ``type_`` must be a recursive type.
    return (
        isinstance(type_.__origin__, typing._SpecialForm)
        and type_.__origin__._name == 'Union'
    )


def match_optional_type(type_):
    """Return ``T`` for ``typing.Optional[T]``, else ``None``."""
    if len(type_.__args__) != 2:
        return None
    try:
        i = type_.__args__.index(NoneType)
    except ValueError:
        return None
    else:
        return type_.__args__[1 - i]


def type_is_subclass(type_, type_or_tuple):
    """Check sub-class.

    Return false if ``type_`` is a recursive type.
    """
    return isinstance(type_, type) and issubclass(type_, type_or_tuple)
