__all__ = [
    'FileAdapter',
    'FutureAdapter',
    'SocketAdapter',
]

import io
import logging
import os
import socket
import ssl
import weakref

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

    def disown(self):
        target, self.__target = self.__target, None
        return target


class FileAdapter(AdapterBase):
    """File-like adapter.

    NOTE: When adapting a file-like object returned by SSL socket
    makefile, be careful NOT to use read/readinto (even if you provide
    the correct buffer size).  For reasons that I have not figured out
    yet, the BufferedReader returned by makefile can cause SSL socket to
    over-recv, causing the it to hang indefinitely.  For now, the
    solution is to use readinto1.

    NOTE: We do not adapt read1 because in non-blocking mode, read1
    returns b'' both when EOF or when no data is available.
    """

    PROXIED_FIELDS = frozenset([
        'closed',
        'detach',
        'fileno',
    ])

    def __init__(self, file):
        super().__init__(file, self.PROXIED_FIELDS)
        self.__file = file
        os.set_blocking(self.__file.fileno(), False)
        kernel = contexts.get_kernel()
        kernel.notify_open(self.__file.fileno())

        # Keep a weak reference to kernel because we could call
        # `notify_close` in another thread.
        self.__kernel = weakref.ref(kernel)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def disown(self):
        super().disown()
        file, self.__file = self.__file, None
        return file

    async def __call_read(self, func, args):
        while True:
            try:
                ret = func(*args)
                if ret is not None:
                    return ret
            except ssl.SSLWantReadError:
                pass
            await traps.poll_read(self.__file.fileno())

    async def read(self, size=-1):
        return await self.__call_read(self.__file.read, (size, ))

    async def readinto(self, buffer):
        return await self.__call_read(self.__file.readinto, (buffer, ))

    async def readinto1(self, buffer):
        return await self.__call_read(self.__file.readinto1, (buffer, ))

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
        if self.__file is None:
            return  # Disowned.
        if self.__file.raw is None:
            return  # Detached.
        if self.__file.closed:
            return
        kernel = self.__kernel()
        if kernel is not None:
            kernel.notify_close(self.__file.fileno())
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
        'bind',
        'detach',
        'fileno',
        'getsockname',
        'getsockopt',
        'listen',
        'setblocking',
        'setsockopt',
    ])

    READ_BLOCKED = (BlockingIOError, InterruptedError, ssl.SSLWantReadError)
    WRITE_BLOCKED = (BlockingIOError, InterruptedError, ssl.SSLWantWriteError)

    def __init__(self, sock):
        super().__init__(sock, self.PROXIED_FIELDS)
        self.__sock = sock
        self.__sock.setblocking(False)
        kernel = contexts.get_kernel()
        kernel.notify_open(self.__sock.fileno())

        # Keep a weak reference to kernel because we could call
        # `notify_close` in another thread.
        self.__kernel = weakref.ref(kernel)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def disown(self):
        super().disown()
        sock, self.__sock = self.__sock, None
        return sock

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

    async def recv_into(self, buffer, nbytes=0, flags=0):
        while True:
            try:
                return self.__sock.recv_into(buffer, nbytes, flags)
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

    async def sendfile(self, file, offset=0, count=None):
        """Re-implementation of stdlib's socket.sendfile.

        Unlike stdlib's sendfile, this raises TypeError if the file
        argument does not look like a regular file object, rather than
        falling back to send.

        We re-implement stdlib's socket.sendfile because it does not
        support non-blocking sockets.
        """
        self.__sock._check_sendfile_params(file, offset, count)
        # Check whether `file` is a regular file.
        try:
            in_fd = file.fileno()
        except (AttributeError, io.UnsupportedOperation) as exc:
            raise TypeError('expect a regular file') from exc
        try:
            file_size = os.fstat(in_fd).st_size
        except OSError as exc:
            raise TypeError('expect a regular file') from exc
        if file_size == 0:
            return 0
        out_fd = self.__sock.fileno()
        num_to_send = file_size if count is None else count
        num_sent_total = 0
        try:
            while num_to_send > 0:
                try:
                    num_sent = os.sendfile(out_fd, in_fd, offset, num_to_send)
                except self.WRITE_BLOCKED:
                    await traps.poll_write(out_fd)
                    continue
                except (BrokenPipeError, ConnectionResetError):
                    # Avoid these errors caught by `except OSError`.
                    raise
                except OSError as exc:
                    if num_sent_total == 0:
                        # Most likely `file` is not a regular file.
                        raise TypeError('expect a regular file') from exc
                    raise
                if num_sent == 0:
                    break  # EOF of in_fd.
                offset += num_sent
                num_sent_total += num_sent
                num_to_send -= num_sent
            return num_sent_total
        finally:
            if num_sent_total > 0 and hasattr(file, 'seek'):
                file.seek(offset)

    def close(self):
        if self.__sock is None:
            return  # Disowned.
        fd = self.__sock.fileno()
        if fd >= 0:
            kernel = self.__kernel()
            if kernel is not None:
                kernel.notify_close(fd)
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
        'set_finalizer',
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
