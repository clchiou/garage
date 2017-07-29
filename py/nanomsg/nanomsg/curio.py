__all__ = [
    'Socket',
]

import ctypes

import curio.io
import curio.traps

from . import Message, SocketBase
from . import errors
from .constants import AF_SP, NN_DONTWAIT


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
        errors.asserts(self.fd is not None, 'expect socket.fd')

        if self.__sndfd_fileno is None:
            self.__sndfd_fileno = curio.io._Fd(self.options.nn_sndfd)

        flags |= NN_DONTWAIT

        if isinstance(message, Message):
            transmit = super()._send_message
            args = (message, flags)
        else:
            if size is None:
                size = len(message)
            transmit = super()._send_buffer
            args = (message, size, flags)

        return await self.__transmit(self.__sndfd_fileno, transmit, args)

    async def recv(self, message=None, size=None, flags=0):
        errors.asserts(self.fd is not None, 'expect socket.fd')

        if self.__rcvfd_fileno is None:
            self.__rcvfd_fileno = curio.io._Fd(self.options.nn_rcvfd)

        flags |= NN_DONTWAIT

        if message is None:
            transmit = super()._recv_message
            args = (ctypes.c_void_p(), flags)
        else:
            errors.asserts(size is not None, 'expect size')
            transmit = super()._recv_buffer
            args = (message, size, flags)

        return await self.__transmit(self.__rcvfd_fileno, transmit, args)

    async def __transmit(self, fileno, transmit, args):
        while True:
            if self.fd is None:
                # It's closed while we were blocked.
                raise errors.EBADF
            try:
                return transmit(*args)
            except errors.EAGAIN:
                pass
            await curio.traps._read_wait(fileno)
