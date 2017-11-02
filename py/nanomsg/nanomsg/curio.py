__all__ = [
    'Socket',
    'device',
    'terminate',
]

import ctypes

import curio
import curio.traps

from . import (
    Message,
    SocketBase,
    errors,
    terminate as _terminate,
)
from .constants import (
    AF_SP,
    NN_DONTWAIT,
    NN_MSG,
)
from ._nanomsg import (
    nn_iovec,
    nn_msghdr,
    nn_recvmsg,
    nn_sendmsg,
)


async def device(sock1, sock2):
    """Re-implement nn_device without threads.

    NOTE: This implementation lacks many sanity checks that nn_device
    perform at the moment.
    """

    def test_fd(sock, fd_name):
        try:
            getattr(sock.options, fd_name)
        except errors.ENOPROTOOPT:
            return False
        else:
            return True

    async def forward_one(s1, s2):

        body = ctypes.c_void_p()

        control = ctypes.c_void_p()

        io_vector = nn_iovec()
        io_vector.iov_base = ctypes.addressof(body)
        io_vector.iov_len = NN_MSG

        header = nn_msghdr()
        ctypes.memset(ctypes.addressof(header), 0x0, ctypes.sizeof(header))
        header.msg_iov = ctypes.pointer(io_vector)
        header.msg_iovlen = 1
        header.msg_control = ctypes.addressof(control)
        header.msg_controllen = NN_MSG

        await s1.recvmsg(header)
        await s2.sendmsg(header)

    async def forward(s1, s2):
        while True:
            try:
                await forward_one(s1, s2)
            except errors.EBADF:
                break

    async with curio.TaskGroup() as group:
        okay = False
        if test_fd(sock1, 'nn_rcvfd') and test_fd(sock2, 'nn_sndfd'):
            await group.spawn(forward(sock1, sock2))
            okay = True
        if test_fd(sock2, 'nn_rcvfd') and test_fd(sock1, 'nn_sndfd'):
            await group.spawn(forward(sock2, sock1))
            okay = True
        if not okay:
            raise AssertionError('incorrect direction: %r, %r', sock1, sock2)
        await group.join()


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


async def terminate():

    # HACK: Mark tasks as ready before close sockets.
    kernel = await curio.traps._get_kernel()
    # Make a copy before modify it.
    items = tuple(kernel._selector.get_map().items())
    for fd, key in items:
        if isinstance(fd, Fd):
            rtask, wtask = key.data
            _mark_ready(kernel, rtask)
            _mark_ready(kernel, wtask)
            kernel._selector.unregister(fd)

    # Now we may close sockets.
    _terminate()


class Socket(SocketBase):

    def __init__(self, *, domain=AF_SP, protocol=None, socket_fd=None):
        super().__init__(domain=domain, protocol=protocol, socket_fd=socket_fd)

        # Fields for tracking info for the close-socket hack.
        self.__kernels_fds = []  # Allow duplications.

    async def __aenter__(self):
        return super().__enter__()

    async def __aexit__(self, *exc_info):
        return super().__exit__(*exc_info)  # XXX: Would this block?

    def close(self):

        # HACK: Mark tasks as ready before close the socket.
        for kernel, fd in self.__kernels_fds:
            try:
                key = kernel._selector.get_key(fd)
            except KeyError:
                continue
            rtask, wtask = key.data
            _mark_ready(kernel, rtask)
            _mark_ready(kernel, wtask)
            kernel._selector.unregister(fd)

        # Now we may close the socket.
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

    async def sendmsg(self, message_header, flags=0):
        errors.asserts(self.fd is not None, 'expect socket.fd')
        return await self.__transmit(
            self.options.nn_sndfd,
            self.__sendmsg,
            (ctypes.pointer(message_header), flags | NN_DONTWAIT),
        )

    def __recvmsg(self, message_header, flags):
        return errors.check(nn_recvmsg(self.fd, message_header, flags))

    async def recvmsg(self, message_header, flags=0):
        errors.asserts(self.fd is not None, 'expect socket.fd')
        return await self.__transmit(
            self.options.nn_rcvfd,
            self.__recvmsg,
            (ctypes.pointer(message_header), flags | NN_DONTWAIT),
        )

    def __sendmsg(self, message_header, flags):
        return errors.check(nn_sendmsg(self.fd, message_header, flags))

    async def __transmit(self, eventfd, transmit, args):

        while True:

            # It's closed while we were blocked.
            if self.fd is None:
                raise errors.EBADF

            try:
                return transmit(*args)
            except errors.EAGAIN:
                pass

            # Wrap eventfd so that terminate() may find it.
            eventfd = Fd(eventfd)

            pair = (await curio.traps._get_kernel(), eventfd)
            self.__kernels_fds.append(pair)
            try:
                await curio.traps._read_wait(eventfd)
            finally:
                self.__kernels_fds.remove(pair)


# A wrapper class for separating out "our" file descriptors.
class Fd(int):
    pass


def _mark_ready(kernel, task):
    if task is None:
        return
    kernel._ready.append(task)
    task.next_value = None
    task.next_exc = None
    task.state = 'READY'
    task.cancel_func = None
