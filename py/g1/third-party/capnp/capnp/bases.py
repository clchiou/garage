"""Optional helper classes for wrapping capnp classes."""

__all__ = [
    'Base',
    'BaseResource',
    'def_f0',
    'def_mp',
    'def_p',
    'get_raw',
    'to_str',
]

import functools
import operator

from g1.bases import classes
from g1.bases import functionals
from g1.bases.assertions import ASSERT


class Base:
    """Wrap value types."""

    _raw_type = type(None)  # Sub-class must override this.

    def __init__(self, raw):
        self._raw = ASSERT.isinstance(raw, self._raw_type)


class BaseResource(Base):
    """Wrap resource types."""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        raw, self._raw = self._raw, None
        raw._reset()

    def __del__(self):
        # In case user forgets to clean it up.
        if self._raw is not None:
            self._raw._reset()


get_raw = operator.attrgetter('_raw')


def _wrap_method(funcs):
    return functionals.compose(*funcs, get_raw)


def def_p(*funcs):
    """Define a property."""
    return property(_wrap_method(funcs))


def def_mp(name, *funcs):
    """Define a memorizing property."""
    wrapper = _wrap_method(funcs)
    wrapper.__name__ = name
    return classes.memorizing_property(wrapper)


def def_f0(*funcs):
    """Define a 0-arg method."""
    return functools.partialmethod(_wrap_method(funcs))


def to_str(bytes_or_buffer):
    # capnp's text objects are always UTF-8 encoded.
    return str(bytes_or_buffer, 'utf-8')
