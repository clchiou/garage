"""Error types."""

__all__ = [
    'ERRORS',
    'NngError',
    'UnknownError',
    'check',
]

from g1.bases import collections

from . import _nng


def check(rv):
    if rv != 0:
        raise make_exc(rv)
    return rv


def make_exc(errno):
    if errno & _nng.nng_errno_enum.NNG_ESYSERR:
        return ERRORS.NNG_ESYSERR(errno)
    elif errno & _nng.nng_errno_enum.NNG_ETRANERR:
        return ERRORS.NNG_ETRANERR(errno)
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
        return _nng.F.nng_strerror(self.args[0]).decode('utf8')


class ErrorMessages(dict):

    def __missing__(self, errno):
        if errno is None:
            raise KeyError(errno)
        return _nng.F.nng_strerror(errno).decode('utf8')


ERROR_MESSAGES = ErrorMessages()


def str_error_with_predefined_message(self):
    return '%s: %s' % (
        self.errno.name,
        ERROR_MESSAGES[self.errno],
    )


def str_error(self):
    return '%s: %s' % (
        self.errno.name,
        _nng.F.nng_strerror(self.args[0]).decode('utf8'),
    )


def make_error_type(errno, str_func):
    return type(
        errno.name,
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

_ERRORS = list(NORMAL_ERROR_TYPES.values())
_ERRORS.extend(
    make_error_type(errno, str_error) for errno in (
        _nng.nng_errno_enum.NNG_ESYSERR,
        _nng.nng_errno_enum.NNG_ETRANERR,
    )
)
ERRORS = collections.Namespace(*((e.__name__, e) for e in _ERRORS))
del _ERRORS
