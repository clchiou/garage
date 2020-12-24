"""Asynchronous nng socket interface."""

__all__ = [
    'Context',
    'Socket',
]

import ctypes

from g1.asyncs import kernels
from g1.asyncs.bases import locks
from g1.bases.assertions import ASSERT

from . import _nng
from . import bases
from . import errors
from . import messages


class Dialer(bases.DialerBase):

    def start(self):
        self._start(flags=_nng.nng_flag_enum.NNG_FLAG_NONBLOCK)


class Socket(bases.SocketBase):

    _dialer_type = Dialer

    def dial(self, url, *, create_only=False):
        return self._dial(
            url,
            flags=_nng.nng_flag_enum.NNG_FLAG_NONBLOCK,
            create_only=create_only,
        )

    async def send(self, data):
        with messages.Message(ASSERT.isinstance(data, bytes)) as message:
            return await self.sendmsg(message)

    async def recv(self):
        with await self.recvmsg() as message:
            return message.body.copy()

    async def sendmsg(self, message):
        return await AioSender(message).run(self._handle)

    async def recvmsg(self):
        return await AioReceiver().run(self._handle)


class Context(bases.ContextBase):

    async def send(self, data):
        with messages.Message(ASSERT.isinstance(data, bytes)) as message:
            return await self.sendmsg(message)

    async def recv(self):
        with await self.recvmsg() as message:
            return message.body.copy()

    async def sendmsg(self, message):
        return await ContextSender(message).run(self._handle)

    async def recvmsg(self):
        return await ContextReceiver().run(self._handle)


class AsyncTransceiverBase:

    async def run(self, handle):

        event = locks.Event()

        kernel = ASSERT.not_none(kernels.get_kernel())
        callback = _nng.nng_aio_callback(
            lambda _: kernel.post_callback(event.set)
        )

        aio_p = _nng.nng_aio_p()
        errors.check(_nng.F.nng_aio_alloc(ctypes.byref(aio_p), callback, None))
        try:

            # Strangely, the default is not ``NNG_DURATION_DEFAULT`` but
            # ``NNG_DURATION_INFINITE``; let's make default the default.
            _nng.F.nng_aio_set_timeout(aio_p, _nng.NNG_DURATION_DEFAULT)

            self.transceive(handle, aio_p)

            try:
                await event.wait()
            except BaseException:
                _nng.F.nng_aio_cancel(aio_p)
                raise

            errors.check(_nng.F.nng_aio_result(aio_p))

            return self.make_result(aio_p)

        finally:

            # Call ``nng_aio_wait`` to ensure that AIO is completed and
            # we may safely read its result or free it (in case we are
            # here due to an exception).
            _nng.F.nng_aio_wait(aio_p)

            self.cleanup(aio_p)

            _nng.F.nng_aio_free(aio_p)

    def transceive(self, handle, aio_p):
        raise NotImplementedError

    def make_result(self, aio_p):
        raise NotImplementedError

    def cleanup(self, aio_p):
        raise NotImplementedError


class AioSender(AsyncTransceiverBase):

    def __init__(self, message):
        super().__init__()
        self.__message = message

    def transceive(self, handle, aio_p):
        _nng.F.nng_aio_set_msg(aio_p, self.__message._get())
        _nng.F.nng_send_aio(handle, aio_p)

    def make_result(self, aio_p):
        return None

    def cleanup(self, aio_p):
        if _nng.F.nng_aio_result(aio_p) == 0:
            self.__message.disown()  # Ownership is transferred on success.


class AioReceiver(AsyncTransceiverBase):

    def transceive(self, handle, aio_p):
        _nng.F.nng_recv_aio(handle, aio_p)

    def make_result(self, aio_p):
        return messages.Message(msg_p=_nng.F.nng_aio_get_msg(aio_p))

    def cleanup(self, aio_p):
        pass


class ContextSender(AsyncTransceiverBase):

    def __init__(self, message):
        super().__init__()
        self.__message = message

    def transceive(self, handle, aio_p):
        _nng.F.nng_aio_set_msg(aio_p, self.__message._get())
        _nng.F.nng_ctx_send(handle, aio_p)

    def make_result(self, aio_p):
        return None

    def cleanup(self, aio_p):
        if _nng.F.nng_aio_result(aio_p) == 0:
            self.__message.disown()  # Ownership is transferred on success.


class ContextReceiver(AsyncTransceiverBase):

    def transceive(self, handle, aio_p):
        _nng.F.nng_ctx_recv(handle, aio_p)

    def make_result(self, aio_p):
        return messages.Message(msg_p=_nng.F.nng_aio_get_msg(aio_p))

    def cleanup(self, aio_p):
        pass
