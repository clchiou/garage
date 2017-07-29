__all__ = [
    'Socket',
]

import asyncio

from . import SocketBase
from .constants import AF_SP, NN_DONTWAIT
from .errors import EAGAIN


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
        self._sndfd_ready = asyncio.Event(loop=loop)
        self._rcvfd_ready = asyncio.Event(loop=loop)
        # Get sndfd/rcvfd lazily since not all protocols support both.
        self._sndfd_manager = None
        self._rcvfd_manager = None
        self._loop = loop or asyncio.get_event_loop()

    def close(self):
        if self.fd is None:
            return
        super().close()
        # Wake up all waiters in send() and recv().
        self._sndfd_ready.set()
        self._rcvfd_ready.set()

    async def __aenter__(self):
        return super().__enter__()

    async def __aexit__(self, *exc_info):
        return super().__exit__(*exc_info)  # XXX: Would this block?

    async def send(self, message, size=None, flags=0):

        if self._sndfd_manager is None:
            self._sndfd_manager = FileDescriptorManager(
                self.options.nn_sndfd,
                self._sndfd_ready.set,
                self._loop.add_reader,
                self._loop.remove_reader,
            )

        with self._sndfd_manager:
            return await self._async_tx(
                self._sndfd_ready, self._blocking_send, message, size, flags)

    async def recv(self, message=None, size=None, flags=0):

        if self._rcvfd_manager is None:
            self._rcvfd_manager = FileDescriptorManager(
                self.options.nn_rcvfd,
                self._rcvfd_ready.set,
                self._loop.add_reader,
                self._loop.remove_reader,
            )

        with self._rcvfd_manager:
            return await self._async_tx(
                self._rcvfd_ready, self._blocking_recv, message, size, flags)

    async def _async_tx(self, ready, tx, message, size, flags):
        if self.fd is None:
            raise AssertionError
        flags |= NN_DONTWAIT.value
        while True:
            await ready.wait()  # Many watiers could be waited at this point.
            if self.fd is None:
                raise AssertionError
            try:
                return tx(message, size, flags)
            except EAGAIN:
                pass
            ready.clear()  # Wait for the next readiness event.
