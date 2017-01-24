__all__ = [
    'Socket',
]

import curio.io
import curio.traps

from . import SocketBase
from .constants import (
    AF_SP,
    NN_DONTWAIT,
)
from .errors import (
    Closed,
    NanomsgEagain,
)


class Socket(SocketBase):

    def __init__(self, *, domain=AF_SP, protocol=None, socket_fd=None):
        super().__init__(domain=domain, protocol=protocol, socket_fd=socket_fd)
        # Get sndfd/rcvfd lazily since not all protocols support both.
        self.__sndfd_fileno = None
        self.__rcvfd_fileno = None

    async def __aenter__(self):
        return super().__enter__()

    async def __aexit__(self, *exc_info):
        return super().__exit__(*exc_info)  # XXX: Would this block?

    async def send(self, message, size=None, flags=0):
        if self.fd is None:
            raise Closed
        if self.__sndfd_fileno is None:
            self.__sndfd_fileno = curio.io._Fd(self.options.sndfd)
        return await self._async_tx(
            self.__sndfd_fileno, self._blocking_send, message, size, flags)

    async def recv(self, message=None, size=None, flags=0):
        if self.fd is None:
            raise Closed
        if self.__rcvfd_fileno is None:
            self.__rcvfd_fileno = curio.io._Fd(self.options.rcvfd)
        return await self._async_tx(
            self.__rcvfd_fileno, self._blocking_recv, message, size, flags)

    async def _async_tx(self, fileno, blocking_tx, message, size, flags):
        flags |= NN_DONTWAIT
        while True:
            if self.fd is None:
                raise Closed
            try:
                return blocking_tx(message, size, flags)
            except NanomsgEagain:
                await curio.traps._read_wait(fileno)
