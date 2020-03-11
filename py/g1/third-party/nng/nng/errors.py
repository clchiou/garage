"""Error types."""

__all__ = [
    'Errors',
    'NngError',
    'UnknownError',
    'check',
]

from g1.bases import collections
from g1.bases.assertions import ASSERT

from . import _nng


def check(rv):
    if rv != 0:
        raise make_exc(rv)
    return rv


def make_exc(errno):
    if errno & _nng.nng_errno_enum.NNG_ESYSERR:
        return Errors.ESYSERR(errno)
    elif errno & _nng.nng_errno_enum.NNG_ETRANERR:
        return Errors.ETRANERR(errno)
    else:
        try:
            return NORMAL_ERROR_TYPES[errno]()
        except KeyError:
            return UnknownError(errno)


class NngError(Exception):
    """Base error type."""


class UnknownError(NngError):

    def __str__(self):
        # pylint: disable=unsubscriptable-object
        return _nng.F.nng_strerror(self.args[0]).decode('utf-8')


def _load_str_error(errno):
    if errno is None:
        raise KeyError(errno)
    return _nng.F.nng_strerror(errno).decode('utf-8')


ERROR_MESSAGES = collections.LoadingDict(_load_str_error)


def str_error_with_predefined_message(self):
    return '%s: %s' % (
        self.errno.name,
        ERROR_MESSAGES[self.errno],
    )


def str_error(self):
    return '%s: %s' % (
        self.errno.name,
        _nng.F.nng_strerror(self.args[0]).decode('utf-8'),
    )


def make_error_type(errno, str_func):
    return type(
        ASSERT.startswith(errno.name, 'NNG_')[4:],
        (NngError, ),
        {
            'errno': errno,
            '__str__': str_func,
        },
    )


NORMAL_ERROR_TYPES = {
    errno: make_error_type(errno, str_error_with_predefined_message)
    for errno in _nng.nng_errno_enum
    if errno not in (
        _nng.nng_errno_enum.NNG_ESYSERR,
        _nng.nng_errno_enum.NNG_ETRANERR,
    )
}

Errors = collections.Namespace(
    *((e.__name__, e) for e in NORMAL_ERROR_TYPES.values()),
    *((e.__name__, e) for e in (
        make_error_type(_nng.nng_errno_enum.NNG_ESYSERR, str_error),
        make_error_type(_nng.nng_errno_enum.NNG_ETRANERR, str_error),
    )),
)
