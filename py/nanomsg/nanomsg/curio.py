__all__ = [
    'Socket',
]

import ctypes

import curio.traps

from . import Message, SocketBase
from . import errors
from .constants import AF_SP, NN_DONTWAIT


#
# Note about the hack:
#
# After a file descriptor (specifically, nn_sndfd, and nn_rcvfd) is
# added to curio's event loop, it can't to detect when file descriptor
# is closed.  As a result, __transmit will be blocked forever on waiting
# the file descriptor becoming readable.
#
# To address this issue, before we close the socket, we will get the
# curio kernel object, and mark the blocked tasks as ready manually.
#
class Socket(SocketBase):

    def __init__(self, *, domain=AF_SP, protocol=None, socket_fd=None):
        super().__init__(domain=domain, protocol=protocol, socket_fd=socket_fd)

        # Fields for tracking info for the close-socket hack.
        self.__kernel = None
        self.__fds = set()

    async def __aenter__(self):
        return super().__enter__()

    async def __aexit__(self, *exc_info):
        return super().__exit__(*exc_info)  # XXX: Would this block?

    def close(self):

        # HACK: Mark tasks as ready before close the socket.
        if self.__kernel:
            for fd in self.__fds:
                key = self.__kernel._selector.get_key(fd)
                if key:
                    rtask, wtask = key.data
                    if rtask:
                        self.__mark_ready(rtask)
                    if wtask:
                        self.__mark_ready(wtask)

        # Now we may close the socket.
        super().close()

    def __mark_ready(self, task):
        self.__kernel._ready.append(task)
        task.next_value = None
        task.next_exc = None
        task.state = 'READY'
        task.cancel_func = None

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

            kernel = await curio.traps._get_kernel()
            assert self.__kernel in (None, kernel), (
                'socket is accessed by different kernels: %r != %r' %
                (self.__kernel, kernel)
            )

            self.__kernel = kernel
            self.__fds.add(eventfd)
            try:
                await curio.traps._read_wait(eventfd)
            finally:
                self.__kernel = None
                self.__fds.remove(eventfd)
