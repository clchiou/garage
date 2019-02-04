__all__ = [
    'CompletionQueueAdapter',
    'FileAdapter',
    'FutureAdapter',
    'SocketAdapter',
]

import os
import socket
import ssl

from g1.bases.assertions import ASSERT

from . import contexts
from . import traps

try:
    from g1.threads import queues
except ImportError:
    queues = None


class AdapterBase:

    def __init__(self, target, fields):
        self.__target = target
        self.__fields = ASSERT.not_contains(fields, 'target')

    def __repr__(self):
        return '<%s at %#x: %r>' % (
            self.__class__.__qualname__,
            id(self),
            self.__target,
        )

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

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

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

    async def close(self):
        if self.__file.closed:
            return
        # Pre-fetch file descriptor before file is closed.
        fd = self.__file.fileno()
        while True:
            try:
                self.__file.close()
                break
            except (BlockingIOError, InterruptedError):
                pass
            if self.__file.closed:
                # If nothing to be flushed out, let's break out.
                break
            else:
                await traps.poll_write(self.__file.fileno())
        contexts.get_kernel().close_fd(fd)


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

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

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

    async def close(self):
        # I assume that ``socket.close`` does not flush out data, and
        # thus never raises ``BlockingIOError``, etc., but for
        # consistency, let's still declare it as an async function.
        fd = self.__sock.fileno()
        self.__sock.close()
        # If ``fd < 0``, it means the socket has been closed.
        if fd >= 0:
            contexts.get_kernel().close_fd(fd)


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
            lambda: self.__future.add_callback(
                lambda _: kernel.post_callback(callback)
            ),
        )

    async def get_result(self):
        await self.join()
        return self.__future.get_result()

    async def get_exception(self):
        await self.join()
        return self.__future.get_exception()


class CompletionQueueAdapter(AdapterBase):

    PROXIED_FIELDS = frozenset([
        'is_closed',
        'close',
        'put',
    ])

    def __init__(self, completion_queue):
        super().__init__(completion_queue, self.PROXIED_FIELDS)
        self.__completion_queue = completion_queue

    def __bool__(self):
        return bool(self.__completion_queue)

    def __len__(self):
        return len(self.__completion_queue)

    async def get(self):
        while True:
            try:
                return self.__completion_queue.get(timeout=0)
            except queues.Empty:
                await traps.block(
                    self.__completion_queue,
                    lambda: self.__completion_queue.add_on_completion_callback(
                        _OnCompletion(
                            self.__completion_queue,
                            contexts.get_kernel(),
                        ),
                    ),
                )

    async def as_completed(self):
        while True:
            try:
                yield await self.get()
            except queues.Closed:
                break


class _OnCompletion:
    """Helper class for dealing with ``CompletionQueue`` callback."""

    def __init__(self, completion_queue, kernel):
        self.completion_queue = completion_queue
        self.kernel = kernel

    def __call__(self, _):
        self.completion_queue.remove_on_completion_callback(self)
        self.kernel.post_callback(self.callback)

    def callback(self):
        self.kernel.unblock(self.completion_queue)
