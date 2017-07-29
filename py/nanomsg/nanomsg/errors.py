__all__ = [
    'NanomsgError',
    # Extend in _create_errors().
]

from . import _nanomsg as _nn
from .constants import Error


_ERRORS = {}


class NanomsgError(Exception):
    """Base exception class."""

    @staticmethod
    def make(error):
        exc_class = _ERRORS.get(error)
        if exc_class is None:
            return NanomsgError(error, _nn.nn_strerror(error).decode('ascii'))
        else:
            return exc_class()

    def __init__(self, error, message):
        super().__init__(message)
        self.error = error


def _create_errors(global_vars, exposed_names):

    def make_init(error):
        # Don't use super() - its magic doesn't work here.
        message = _nn.nn_strerror(error).decode('ascii')
        def __init__(self):
            NanomsgError.__init__(self, error, message)
        return __init__

    for error in Error:
        exposed_names.append(error.name)
        global_vars[error.name] = _ERRORS[error] = type(
            error.name,
            (NanomsgError,),
            {'__init__': make_init(error)},
        )


def check(ret):
    if ret == -1:
        raise NanomsgError.make(_nn.nn_errno())
    return ret


_create_errors(globals(), __all__)
