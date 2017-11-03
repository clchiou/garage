__all__ = [
    'Socket',
]

import asyncio
import ctypes

from . import Message, MessageBuffer, SocketBase
from . import errors
from .constants import AF_SP, NN_DONTWAIT


class FileDescriptorManager:

    def __init__(self, fd, cb, add_watcher, remove_watcher):
        self.fd = fd
        self.cb = cb
        self.add_watcher = add_watcher
        self.remove_watcher = remove_watcher
        self.num_waiters = 0

    def __enter__(self):
        if self.num_waiters == 0:
            self.add_watcher(self.fd, self.cb)
        self.num_waiters += 1

    def __exit__(self, *_):
        self.num_waiters -= 1
        if self.num_waiters == 0:
            self.remove_watcher(self.fd)


class Socket(SocketBase):

    def __init__(self, *, domain=AF_SP, protocol=None, socket_fd=None,
                 loop=None):
        super().__init__(domain=domain, protocol=protocol, socket_fd=socket_fd)
        self.__sndfd_ready = asyncio.Event(loop=loop)
        self.__rcvfd_ready = asyncio.Event(loop=loop)
        # Get sndfd/rcvfd lazily since not all protocols support both.
        self.__sndfd_manager = None
        self.__rcvfd_manager = None
        self.__loop = loop or asyncio.get_event_loop()

    def close(self):
        if self.fd is None:
            return
        super().close()
        # Wake up all waiters in send() and recv().
        self.__sndfd_ready.set()
        self.__rcvfd_ready.set()

    async def __aenter__(self):
        return super().__enter__()

    async def __aexit__(self, *exc_info):
        return super().__exit__(*exc_info)  # XXX: Would this block?

    async def send(self, message, size=None, flags=0):
        errors.asserts(self.fd is not None, 'expect socket.fd')
        errors.asserts(
            not isinstance(message, Message), 'send does not accept Message')

        if self.__sndfd_manager is None:
            self.__sndfd_manager = FileDescriptorManager(
                self.options.nn_sndfd,
                self.__sndfd_ready.set,
                self.__loop.add_reader,
                self.__loop.remove_reader,
            )

        flags |= NN_DONTWAIT

        if isinstance(message, MessageBuffer):
            transmit = super()._send_message_buffer
            args = (message, flags)
        else:
            if size is None:
                size = len(message)
            transmit = super()._send_buffer
            args = (message, size, flags)

        with self.__sndfd_manager:
            return await self.__transmit(self.__sndfd_ready, transmit, args)

    async def recv(self, message=None, size=None, flags=0):
        errors.asserts(self.fd is not None, 'expect socket.fd')
        errors.asserts(
            not isinstance(message, Message), 'recv does not accept Message')

        if self.__rcvfd_manager is None:
            self.__rcvfd_manager = FileDescriptorManager(
                self.options.nn_rcvfd,
                self.__rcvfd_ready.set,
                self.__loop.add_reader,
                self.__loop.remove_reader,
            )

        flags |= NN_DONTWAIT

        if message is None:
            transmit = super()._recv_message_buffer
            args = (ctypes.c_void_p(), flags)
        else:
            errors.asserts(size is not None, 'expect size')
            transmit = super()._recv_buffer
            args = (message, size, flags)

        with self.__rcvfd_manager:
            return await self.__transmit(self.__rcvfd_ready, transmit, args)

    async def __transmit(self, ready, transmit, args):
        while True:
            await ready.wait()  # Many watiers could be waited at this point.
            if self.fd is None:
                # It's closed while we were blocked.
                raise errors.EBADF
            try:
                return transmit(*args)
            except errors.EAGAIN:
                pass
            ready.clear()  # Wait for the next readiness event.
