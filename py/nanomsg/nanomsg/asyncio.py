__all__ = [
    'Socket',
]

import asyncio

from . import SocketBase
from . import errors
from .constants import AF_SP
from .constants import Error


class Socket(SocketBase):

    def __init__(self, *, domain=AF_SP, protocol=None, socket_fd=None,
                 loop=None):
        super().__init__(domain=domain, protocol=protocol, socket_fd=socket_fd)

        self._loop = loop or asyncio.get_event_loop()

        sndfd = None
        try:
            sndfd = self.options.sndfd
        except errors.NanomsgError as err:
            if err.errno is not Error.ENOPROTOOPT:
                raise
        if sndfd is None:
            self._sndfd_ready = None
        else:
            self._sndfd_ready = asyncio.Event(loop=self._loop)
            self._loop.add_writer(sndfd, self._sndfd_ready.set)

        rcvfd = None
        try:
            rcvfd = self.options.rcvfd
        except errors.NanomsgError as err:
            if err.errno is not Error.ENOPROTOOPT:
                raise
        if rcvfd is None:
            self._rcvfd_ready = None
        else:
            self._rcvfd_ready = asyncio.Event(loop=self._loop)
            self._loop.add_reader(rcvfd, self._rcvfd_ready.set)

    def close(self):
        if self.fd is None:
            return
        if self._sndfd_ready is not None:
            self._loop.remove_writer(self.options.sndfd)
        if self._rcvfd_ready is not None:
            self._loop.remove_reader(self.options.rcvfd)
        super().close()

    async def send(self, message, size=None, flags=0):
        if self.fd is None or self._sndfd_ready is None:
            raise AssertionError
        await self._sndfd_ready.wait()
        self._sndfd_ready.clear()
        return self._blocking_send(message, size, flags)

    async def recv(self, message=None, size=None, flags=0):
        if self.fd is None or self._rcvfd_ready is None:
            raise AssertionError
        await self._rcvfd_ready.wait()
        self._rcvfd_ready.clear()
        return self._blocking_recv(message, size, flags)
