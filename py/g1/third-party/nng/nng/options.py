"""Helper for accessing options through object property."""

__all__ = [
    'OptionsBase',
    'make',
    'getopt_string',
    'setopt_opaque',
    'setopt_string',
]

import ctypes
import datetime
import functools

from g1.bases import classes
from g1.bases.assertions import ASSERT

from . import _nng
from . import errors

ONE_MILLISECOND = datetime.timedelta(milliseconds=1)


class OptionsBase:

    _handle = classes.abstract_property
    _getopt_prefix = classes.abstract_property
    _setopt_prefix = classes.abstract_property


def make(option, *, mode=None):
    """Make a property for accessing an option.

    It assumes that the Python object defines these attributes:
    `_handle`, `_getopt_prefix`, and `_setopt_prefix`.
    """

    name, type_name, default_mode = option
    if mode is None:
        mode = default_mode

    if type_name in ('bool', 'int', 'size', 'uint64'):
        getter = get_simple
        setter = set_simple
    elif type_name == 'ms':
        getter = get_duration
        setter = set_duration
    elif type_name == 'string':
        getter = get_string
        setter = set_string
    elif type_name == 'sockaddr':
        getter = get_sockaddr
        setter = set_sockaddr
    else:
        ASSERT.unreachable('unsupported option type: {}', type_name)

    kwargs = {}

    if mode in ('ro', 'rw'):
        kwargs['fget'] = functools.partial(
            getter, name=name, type_name=type_name
        )

    if mode in ('wo', 'rw'):
        kwargs['fset'] = functools.partial(
            setter, name=name, type_name=type_name
        )

    return property(**ASSERT.not_empty(kwargs))


def get_simple(self, *, name, type_name):
    getopt = _nng.F['%s_%s' % (self._getopt_prefix, type_name)]
    value = _nng.OPTION_TYPES[type_name][1]()
    errors.check(getopt(self._handle, name, ctypes.byref(value)))
    return value.value


def set_simple(self, value, *, name, type_name):
    setopt = _nng.F['%s_%s' % (self._setopt_prefix, type_name)]
    errors.check(setopt(self._handle, name, value))


def get_duration(self, *, name, type_name):
    ASSERT.equal(type_name, 'ms')
    value = get_simple(self, name=name, type_name='ms')
    if value >= 0:
        return datetime.timedelta(milliseconds=value)
    else:
        return _nng.Durations(value)


def set_duration(self, value, **kwargs):
    ASSERT.equal(kwargs.get('type_name'), 'ms')
    if isinstance(value, datetime.timedelta):
        value = int(value / ONE_MILLISECOND + 0.5)
    set_simple(self, value, **kwargs)


def get_sockaddr(self, *, name, type_name):
    ASSERT.equal(type_name, 'sockaddr')
    getopt = _nng.F['%s_sockaddr' % self._getopt_prefix]
    value = _nng.nng_sockaddr()
    errors.check(getopt(self._handle, name, ctypes.byref(value)))
    return value


def set_sockaddr(self, value, *, name, type_name):
    ASSERT.equal(type_name, 'sockaddr')
    setopt = _nng.F[self._setopt_prefix]
    errors.check(
        setopt(self._handle, name, ctypes.byref(value), ctypes.sizeof(value))
    )


def get_string(self, *, name, type_name):
    ASSERT.equal(type_name, 'string')
    getopt = _nng.F['%s_string' % self._getopt_prefix]
    value = ctypes.c_char_p()
    errors.check(getopt(self._handle, name, ctypes.byref(value)))
    try:
        return value.value.decode('utf-8')  # pylint: disable=no-member
    finally:
        _nng.F.nng_strfree(value)


def set_string(self, value, *, name, type_name):
    ASSERT.equal(type_name, 'string')
    setopt = _nng.F['%s_string' % self._setopt_prefix]
    errors.check(setopt(self._handle, name, _nng.ensure_bytes(value)))


def getopt_string(self, name):
    return get_string(self, name=name, type_name='string')


def setopt_string(self, name, value):
    return set_string(self, name=name, value=value, type_name='string')


def setopt_opaque(self, name, value):
    ASSERT.isinstance(value, bytes)
    setopt = _nng.F[self._setopt_prefix]
    errors.check(setopt(self._handle, name, value, len(value)))
