__all__ = [
    'FileAdapter',
    'FutureAdapter',
    'SocketAdapter',
]

import logging
import os
import socket
import ssl

from g1.asyncs.kernels import contexts
from g1.asyncs.kernels import traps
from g1.bases import classes
from g1.bases.assertions import ASSERT

LOG = logging.getLogger(__name__)


class AdapterBase:

    def __init__(self, target, fields):
        self.__target = target
        self.__fields = ASSERT.not_contains(fields, 'target')

    __repr__ = classes.make_repr('{self._AdapterBase__target!r}')

    def __getattr__(self, name):
        if name == 'target':
            return self.__target
        if name in self.__fields:
            return getattr(self.__target, name)
        raise AttributeError('disallow accessing field: %s' % name)


class FileAdapter(AdapterBase):

    PROXIED_FIELDS = frozenset([
        'closed',
        'fileno',
    ])

    def __init__(self, file):
        super().__init__(file, self.PROXIED_FIELDS)
        self.__file = file
        os.set_blocking(self.__file.fileno(), False)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    async def read(self, size=-1):
        while True:
            data = self.__file.read(size)
            if data is not None:
                return data
            await traps.poll_read(self.__file.fileno())

    async def write(self, data):
        while True:
            try:
                num_written = self.__file.write(data)
                if num_written is not None:
                    return num_written
            except (BlockingIOError, InterruptedError) as exc:
                if exc.characters_written > 0:
                    return exc.characters_written
            await traps.poll_write(self.__file.fileno())

    async def flush(self):
        while True:
            try:
                return self.__file.flush()
            except (BlockingIOError, InterruptedError):
                await traps.poll_write(self.__file.fileno())

    def close(self):
        if self.__file.closed:
            return
        try:
            contexts.get_kernel().close_fd(self.__file.fileno())
        except LookupError:
            pass
        try:
            self.__file.close()
        except (BlockingIOError, InterruptedError) as exc:
            # Sadly, there is nothing we can do here since the file has
            # been closed and not-yet-flushed-out data are lost.  If you
            # want absolutely no data loss, you should call ``flush``
            # before call ``close``.
            LOG.warning('close error: %r', self, exc_info=exc)


class SocketAdapter(AdapterBase):

    PROXIED_FIELDS = frozenset([
        'fileno',
        'bind',
        'listen',
        'getsockopt',
        'setsockopt',
    ])

    READ_BLOCKED = (BlockingIOError, InterruptedError, ssl.SSLWantReadError)
    WRITE_BLOCKED = (BlockingIOError, InterruptedError, ssl.SSLWantWriteError)

    def __init__(self, sock):
        super().__init__(sock, self.PROXIED_FIELDS)
        self.__sock = sock
        self.__sock.setblocking(False)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    async def accept(self):
        while True:
            try:
                sock, addr = self.__sock.accept()
                return type(self)(sock), addr
            except self.READ_BLOCKED:
                await traps.poll_read(self.__sock.fileno())

    async def connect(self, address):
        # ``connect`` may raise ``BlockingIOError`` and we should wait
        # until it becomes writeable (but in general, non-blocking
        # connect is weird).
        try:
            self.__sock.connect(address)
        except self.WRITE_BLOCKED:
            await traps.poll_write(self.__sock.fileno())
        errno = self.__sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if errno:
            raise OSError(errno, 'err in connect(%r): %r' % (address, self))
        if getattr(self.__sock, 'do_handshake_on_connect', False):
            await self.do_handshake()

    async def do_handshake(self):
        while True:
            try:
                return self.__sock.do_handshake(block=False)
            except self.READ_BLOCKED:
                await traps.poll_read(self.__sock.fileno())
            except self.WRITE_BLOCKED:
                await traps.poll_write(self.__sock.fileno())

    async def recv(self, buffersize, flags=0):
        while True:
            try:
                return self.__sock.recv(buffersize, flags)
            except self.READ_BLOCKED:
                await traps.poll_read(self.__sock.fileno())

    async def send(self, data, flags=0):
        while True:
            try:
                return self.__sock.send(data, flags)
            except self.WRITE_BLOCKED:
                await traps.poll_write(self.__sock.fileno())

    async def sendmsg(self, buffers, *args):
        while True:
            try:
                return self.__sock.sendmsg(buffers, *args)
            except self.WRITE_BLOCKED:
                await traps.poll_write(self.__sock.fileno())

    def close(self):
        fd = self.__sock.fileno()
        if fd >= 0:
            try:
                contexts.get_kernel().close_fd(fd)
            except LookupError:
                pass
        # I assume that ``socket.close`` does not flush out data, and
        # thus never raises ``BlockingIOError``, etc.
        self.__sock.close()


class FutureAdapter(AdapterBase):

    PROXIED_FIELDS = frozenset([
        'is_completed',
        'add_callback',
        'catching_exception',
        'set_result',
        'set_exception',
    ])

    def __init__(self, future):
        super().__init__(future, self.PROXIED_FIELDS)
        self.__future = future

    async def join(self):
        if self.__future.is_completed():
            return
        # Since the callback could be fired from another thread, which
        # may not have the right kernel object in its context, we should
        # get the right kernel object from the context here, and pass it
        # to the callback function.
        kernel = contexts.get_kernel()
        callback = lambda: kernel.unblock(self.__future)
        await traps.block(
            self.__future,
            lambda: self.__future.
            add_callback(lambda _: kernel.post_callback(callback)),
        )
        ASSERT.true(self.__future.is_completed())

    async def get_result(self):
        await self.join()
        return self.__future.get_result(timeout=0)

    async def get_exception(self):
        await self.join()
        return self.__future.get_exception(timeout=0)
