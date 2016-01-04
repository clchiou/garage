__all__ = [
    'NanomsgError',
    'NanomsgEagain',
]

from . import _nanomsg as _nn
from .constants import Error


class NanomsgError(Exception):

    def __init__(self, errno=None):
        if errno is None:
            errno = _nn.nn_errno()
        super().__init__(_nn.nn_strerror(errno).decode('ascii'))
        self.errno = Error(errno)


class NanomsgEagain(Exception):
    pass


def check(ret):
    if ret == -1:
        raise NanomsgError()
    return ret
