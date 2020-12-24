"""Message interface."""

__all__ = [
    'Message',
]

import ctypes

from g1.bases import classes
from g1.bases import lifecycles
from g1.bases.assertions import ASSERT
from g1.bases.ctypes import (
    PyBUF_WRITE,
    PyMemoryView_FromMemory,
)

from . import _nng
from . import errors


class Message:

    def __init__(self, data=b'', *, msg_p=None):

        # In case ``__init__`` raises.
        self._msg_p = None

        ASSERT.isinstance(data, bytes)

        if msg_p is None:
            msg_p = _nng.nng_msg_p()
            errors.check(_nng.F.nng_msg_alloc(ctypes.byref(msg_p), len(data)))
            if data:
                ctypes.memmove(_nng.F.nng_msg_body(msg_p), data, len(data))

        else:
            # We are taking ownership of ``msg_p`` and should not take
            # any initial data.
            ASSERT.false(data)

        self._msg_p = msg_p
        self.header = Header(self._get)
        self.body = Body(self._get)

        lifecycles.monitor_object_aliveness(self)
        # Our goal is to track all message allocation (by nng_msg_alloc,
        # nng_recv_aio, etc.).  We could add a `add_to` call to all call
        # sites, but it is quite easy to be forgotten, and somewhat
        # breaks the encapsulation of Message.  So instead we call
        # `add_to` here.  The downside of this is that now whenever you
        # construct a Message object without allocating a new new msg_p,
        # e.g., when using disown, you must also decrement the counter.
        lifecycles.add_to((type(self), 'msg_p'), 1)

    __repr__ = classes.make_repr('{self._msg_p}')

    def disown(self):
        msg_p, self._msg_p = self._msg_p, None
        # We have to decrement the counter in disown because we
        # automatically increment it in __init__.
        lifecycles.add_to((type(self), 'msg_p'), -1)
        return msg_p

    def copy(self):
        msg_p = _nng.nng_msg_p()
        errors.check(_nng.F.nng_msg_dup(ctypes.byref(msg_p), self._get()))
        return type(self)(msg_p=msg_p)

    def _get(self):
        return ASSERT.not_none(self._msg_p)

    def __del__(self):
        # You have to check whether ``__init__`` raises.
        if self._msg_p is not None:
            _nng.F.nng_msg_free(self._msg_p)
            lifecycles.add_to((type(self), 'msg_p'), -1)


class Chunk:

    _chunk_get = classes.abstract_method
    _chunk_len = classes.abstract_method
    _chunk_append = classes.abstract_method
    _chunk_clear = classes.abstract_method

    def __init__(self, get):
        self._get = get

    def __bool__(self):
        return len(self) != 0

    def __len__(self):
        return self._chunk_len(self._get())

    def append(self, data):
        ASSERT.isinstance(data, bytes)
        errors.check(self._chunk_append(self._get(), data, len(data)))

    def clear(self):
        self._chunk_clear(self._get())

    def copy(self):
        msg_p = self._get()
        return ctypes.string_at(self._chunk_get(msg_p), self._chunk_len(msg_p))

    @property
    def memory_view(self):
        """Danger!  Make a writable memory view."""
        msg_p = self._get()
        return PyMemoryView_FromMemory(
            self._chunk_get(msg_p),
            self._chunk_len(msg_p),
            # Should we expose a read-only memory view instead?
            PyBUF_WRITE,
        )


class Header(Chunk):

    _chunk_get = _nng.F.nng_msg_header
    _chunk_len = _nng.F.nng_msg_header_len
    _chunk_append = _nng.F.nng_msg_header_append
    _chunk_clear = _nng.F.nng_msg_header_clear


class Body(Chunk):

    _chunk_get = _nng.F.nng_msg_body
    _chunk_len = _nng.F.nng_msg_len
    _chunk_append = _nng.F.nng_msg_append
    _chunk_clear = _nng.F.nng_msg_clear
