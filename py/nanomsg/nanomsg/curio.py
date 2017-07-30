__all__ = [
    'Socket',
]

import ctypes

import curio.traps

# For the workaround...
from garage import asyncs

from . import Message, SocketBase
from . import errors
from .constants import AF_SP, NN_DONTWAIT


#
# Note about workaround:
#
# After a file descriptor (specifically, nn_sndfd, and nn_rcvfd) is
# added to curio's event loop, it doesn't seem to be able to detect that
# file descriptor is closed.  As a result, __transmit will be blocked
# forever on waiting the file descriptor becoming readable.
#
# I honestly don't know how to fix this properly, but here is a my
# workaround: Instead of directly await'ing on _read_wait, let's spawn a
# task for that.  And in close(), we will cancel all of these tasks, in
# the hope that this will unblock all __transmit calls.
#
class Socket(SocketBase):

    def __init__(self, *, domain=AF_SP, protocol=None, socket_fd=None):
        super().__init__(domain=domain, protocol=protocol, socket_fd=socket_fd)
        self.__tasks = asyncs.TaskSet()
        self.__tasks.ignore_done_tasks()  # I don't care about done tasks.
        self.__close_event = asyncs.Event()
        # Defer creation of close_task because task spawning is async,
        # which can't be called in __init__.
        self.__close_task = None

    async def __aenter__(self):
        return super().__enter__()

    async def __aexit__(self, *exc_info):
        return super().__exit__(*exc_info)  # XXX: Would this block?

    async def __on_close(self):
        # The context will cancel all pending tasks on its way out.
        async with self.__tasks:
            await self.__close_event.wait()

    def close(self):
        self.__close_event.set()
        super().close()

    async def send(self, message, size=None, flags=0):
        errors.asserts(self.fd is not None, 'expect socket.fd')

        flags |= NN_DONTWAIT

        if isinstance(message, Message):
            transmit = super()._send_message
            args = (message, flags)
        else:
            if size is None:
                size = len(message)
            transmit = super()._send_buffer
            args = (message, size, flags)

        return await self.__transmit(self.options.nn_sndfd, transmit, args)

    async def recv(self, message=None, size=None, flags=0):
        errors.asserts(self.fd is not None, 'expect socket.fd')

        flags |= NN_DONTWAIT

        if message is None:
            transmit = super()._recv_message
            args = (ctypes.c_void_p(), flags)
        else:
            errors.asserts(size is not None, 'expect size')
            transmit = super()._recv_buffer
            args = (message, size, flags)

        return await self.__transmit(self.options.nn_rcvfd, transmit, args)

    async def __transmit(self, eventfd, transmit, args):

        while True:

            # It's closed while we were blocked.
            if self.fd is None:
                raise errors.EBADF

            try:
                return transmit(*args)
            except errors.EAGAIN:
                pass

            if self.__close_task is None:
                self.__close_task = await asyncs.spawn(
                    self.__on_close(),
                    daemon=True,  # We don't care about joining it.
                )

            task = await self.__tasks.spawn(curio.traps._read_wait(eventfd))
            try:
                await task.wait()
            finally:
                # It is not strictly necessary to cancel this task here,
                # but it is a nice thing to do.
                await task.cancel()
