"""Synchronous nng socket interface."""

__all__ = [
    'Context',
    'Socket',
]

import ctypes
import logging

from g1.bases.assertions import ASSERT

from . import _nng
from . import bases
from . import errors
from . import messages

LOG = logging.getLogger(__name__)


class Dialer(bases.DialerBase):

    def start(self, *, blocking=None):
        if blocking is None:
            try:
                self.start(blocking=True)
            except errors.ERRORS.NNG_ECONNREFUSED as exc:
                LOG.debug('blocking dail error', exc_info=exc)
                self.start(blocking=False)
        else:
            flags = 0 if blocking else _nng.nng_flag_enum.NNG_FLAG_NONBLOCK
            self._start(flags=flags)


class Socket(bases.SocketBase):

    _dialer_type = Dialer

    def dial(self, url, *, blocking=None, create_only=False):
        if create_only:
            return self._dial(url, create_only=create_only)
        elif blocking is None:
            try:
                return self.dial(url, blocking=True)
            except errors.ERRORS.NNG_ECONNREFUSED as exc:
                LOG.debug('blocking dial error', exc_info=exc)
                return self.dial(url, blocking=False)
        else:
            flags = 0 if blocking else _nng.nng_flag_enum.NNG_FLAG_NONBLOCK
            return self._dial(url, flags=flags)

    def send(self, data, *, blocking=True):
        ASSERT.isinstance(data, bytes)
        flags = 0 if blocking else _nng.nng_flag_enum.NNG_FLAG_NONBLOCK
        errors.check(_nng.F.nng_send(self._handle, data, len(data), flags))

    def recv(self, *, blocking=True):
        flags = _nng.nng_flag_enum.NNG_FLAG_ALLOC
        if not blocking:
            flags |= _nng.nng_flag_enum.NNG_FLAG_NONBLOCK
        data = ctypes.c_void_p()
        size = ctypes.c_size_t()
        errors.check(
            _nng.F.nng_recv(
                self._handle,
                ctypes.byref(data),
                ctypes.byref(size),
                flags,
            )
        )
        try:
            return ctypes.string_at(data.value, size.value)
        finally:
            _nng.F.nng_free(data, size)

    def sendmsg(self, message, *, blocking=True):
        flags = 0 if blocking else _nng.nng_flag_enum.NNG_FLAG_NONBLOCK
        errors.check(_nng.F.nng_sendmsg(self._handle, message._get(), flags))
        message.disown()  # Ownership is transferred on success.

    def recvmsg(self, *, blocking=True):
        flags = 0 if blocking else _nng.nng_flag_enum.NNG_FLAG_NONBLOCK
        msg_p = _nng.nng_msg_p()
        errors.check(
            _nng.F.nng_recvmsg(self._handle, ctypes.byref(msg_p), flags)
        )
        return messages.Message(msg_p=msg_p)


class Context(bases.ContextBase):

    def send(self, data, *, blocking=True):
        ASSERT.isinstance(data, bytes)
        return self.sendmsg(messages.Message(data), blocking=blocking)

    def recv(self, *, blocking=True):
        return self.recvmsg(blocking=blocking).body.copy()

    def sendmsg(self, message, *, blocking=True):
        return Sender(message).run(self._handle, blocking)

    def recvmsg(self, *, blocking=True):
        return Receiver().run(self._handle, blocking)


class TransceiverBase:

    def run(self, ctx_handle, blocking):

        aio_p = _nng.nng_aio_p()
        errors.check(_nng.F.nng_aio_alloc(ctypes.byref(aio_p), None, None))
        try:

            if blocking:
                # Strangely, the default is not ``NNG_DURATION_DEFAULT``
                # but ``NNG_DURATION_INFINITE``; let's make default the
                # default.
                _nng.F.nng_aio_set_timeout(aio_p, _nng.NNG_DURATION_DEFAULT)
            else:
                _nng.F.nng_aio_set_timeout(aio_p, _nng.NNG_DURATION_ZERO)

            self.transceive(ctx_handle, aio_p)
            _nng.F.nng_aio_wait(aio_p)

            errors.check(_nng.F.nng_aio_result(aio_p))
            return self.make_result(aio_p)

        finally:
            self.cleanup(aio_p)
            _nng.F.nng_aio_free(aio_p)

    def transceive(self, ctx_handle, aio_p):
        raise NotImplementedError

    def make_result(self, aio_p):
        raise NotImplementedError

    def cleanup(self, aio_p):
        raise NotImplementedError


class Sender(TransceiverBase):

    def __init__(self, message):
        super().__init__()
        self.__message = message

    def transceive(self, ctx_handle, aio_p):
        _nng.F.nng_aio_set_msg(aio_p, self.__message._get())
        _nng.F.nng_ctx_send(ctx_handle, aio_p)

    def make_result(self, aio_p):
        return None

    def cleanup(self, aio_p):
        if _nng.F.nng_aio_result(aio_p) == 0:
            self.__message.disown()  # Ownership is transferred on success.


class Receiver(TransceiverBase):

    def transceive(self, ctx_handle, aio_p):
        _nng.F.nng_ctx_recv(ctx_handle, aio_p)

    def make_result(self, aio_p):
        return messages.Message(msg_p=_nng.F.nng_aio_get_msg(aio_p))

    def cleanup(self, aio_p):
        pass
