"""Utilities for external users."""

__all__ = [
    # Task completion queue.
    'Closed',
    'TaskCompletionQueue',
    # In-memory stream.
    'BytesStream',
    'StringStream',
]

import collections
import io
import logging

from g1.bases.assertions import ASSERT

from . import contexts
from . import errors
from . import locks

LOG = logging.getLogger(__name__)


class Closed(Exception):
    pass


class TaskCompletionQueue:
    """Provide queue-like interface on waiting for task completion.

    NOTE: It does not support future objects; this simplifies its
    implementation, and thus may be more efficient.
    """

    def __init__(self):
        self._gate = locks.Gate()
        self._completed = collections.deque()
        self._uncompleted = set()
        self._not_wait_for = set()
        self._closed = False

    def __repr__(self):
        return (
            '<%s at %#x: %s, completed=%d, uncompleted=%d, not_wait_for=%d>'
        ) % (
            self.__class__.__qualname__,
            id(self),
            'closed' if self._closed else 'open',
            len(self._completed),
            len(self._uncompleted),
            len(self._not_wait_for),
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, *_):
        """Reasonable default policy on joining tasks.

        * First, it will close the queue.
        * On normal exit, it will join all remaining tasks (including
          those "not wait for" tasks).
        * On error, it will cancel tasks before joining them.

        This is not guaranteed to fit any use case though.  On those
        cases, you will have to roll your own context manager.
        """
        # Do not call close with ``graceful=False`` to get the remaining
        # tasks because the queue might have been closed already.
        self.close()
        tasks = self._move_tasks()
        if exc_type:
            for task in tasks:
                task.cancel()
        for task in tasks:
            exc = await task.get_exception()
            if not exc:
                pass
            elif isinstance(exc, errors.Cancelled):
                LOG.debug('task is cancelled: %r', task, exc_info=exc)
            else:
                LOG.error('task error: %r', task, exc_info=exc)

    def is_closed(self):
        return self._closed

    def __bool__(self):
        return any((
            self._completed,
            self._uncompleted,
            self._not_wait_for,
        ))

    def __len__(self):
        return sum((
            len(self._completed),
            len(self._uncompleted),
            len(self._not_wait_for),
        ))

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.get()
        except Closed:
            raise StopAsyncIteration

    def close(self, graceful=True):
        if self._closed:
            return []
        if graceful:
            tasks = []
        else:
            tasks = self._move_tasks()
        self._closed = True
        # NOTE: Call ``unblock`` here, not ``unblock_forever``, because
        # there may still be uncompleted tasks in the queue.
        self._gate.unblock()
        return tasks

    def _move_tasks(self):
        tasks = list(self._completed)
        tasks.extend(self._uncompleted)
        tasks.extend(self._not_wait_for)
        self._completed.clear()
        self._uncompleted.clear()
        self._not_wait_for.clear()
        return tasks

    async def get(self):
        while True:
            if self._completed:
                return self._completed.popleft()
            elif self._uncompleted or not self._closed:
                await self._gate.wait()
            else:
                raise Closed

    def put(self, task, *, wait_for_completion=True):
        """Put task into the queue.

        If ``wait_for_completion`` is false, the queue will not wait for
        the task completion; that is, if the task is still not completed
        when ``get`` is called, ``get`` will not be blocked because of
        that (but ``get`` could still be blocked for other reasons).
        """
        if self._closed:
            raise Closed
        if wait_for_completion:
            self._uncompleted.add(task)
            task.add_callback(self._on_completion)
        else:
            self._not_wait_for.add(task)
            task.add_callback(self._on_not_wait_for_completion)

    def spawn(self, awaitable, *, wait_for_completion=True):
        """Spawn and put task to the queue.

        This is equivalent to spawn-then-put, but is better that, if
        ``put`` will fail, no task is spawned.
        """
        if self._closed:
            raise Closed
        task = contexts.get_kernel().spawn(awaitable)
        try:
            self.put(task, wait_for_completion=wait_for_completion)
        except BaseException:
            # This should never happen...
            LOG.critical('put should never fail here: %r, %r', self, task)
            task.cancel()
            raise
        return task

    def _on_completion(self, task):
        if self._uncompleted:
            self._uncompleted.remove(task)
            self._completed.append(task)
        self._gate.unblock()

    def _on_not_wait_for_completion(self, task):
        if self._not_wait_for:
            self._not_wait_for.remove(task)
            self._completed.append(task)
        self._gate.unblock()


class StreamBase:
    """In-memory stream base class.

    The semantics that this class implements is similar to a pipe, not a
    regular file (and ``close`` only closes the write-end of stream).

    Compared to a pipe, this class employs an unbounded buffer, and thus
    a writer is never blocked.

    This class provides both blocking and non-blocking interface.
    """

    def __init__(self, buffer_type, data_type, newline):
        self._buffer_type = buffer_type
        self._data_type = data_type
        self._newline = newline
        self._buffer = self._buffer_type()
        self._closed = False
        self._gate = locks.Gate()

    def _make_buffer(self, data):
        if data:
            buffer = self._buffer_type(data)
            buffer.seek(len(data))
        else:
            buffer = self._buffer_type()
        return buffer

    def __repr__(self):
        return '<%s at %#x: %s>' % (
            self.__class__.__qualname__,
            id(self),
            'closed' if self._closed else 'open',
        )

    async def close(self):
        return self.close_nonblocking()

    def __aiter__(self):
        return self

    async def __anext__(self):
        line = await self.readline()
        if not line:
            raise StopAsyncIteration
        return line

    async def read(self, size=-1):
        while True:
            data = self.read_nonblocking(size)
            if data is None:
                await self._gate.wait()
            else:
                return data

    async def readline(self, size=-1):
        while True:
            line = self.readline_nonblocking(size)
            if line is None:
                await self._gate.wait()
            else:
                return line

    async def readlines(self, hint=None):
        if hint is None or hint <= 0:
            hint = float('+inf')
        lines = []
        num_read = 0
        async for line in self:
            lines.append(line)
            num_read += len(line)
            if num_read >= hint:
                break
        return lines

    async def write(self, data):
        return self.write_nonblocking(data)

    #
    # Non-blocking counterparts.
    #
    # There is no implementation for ``__iter__`` and ``readlines``
    # because their interface is not (easily?) compatible with
    # non-blocking semantics.
    #

    NonblockingMethods = collections.namedtuple(
        'NonblockingMethods',
        (
            'close',
            'read',
            'readline',
            'write',
        ),
    )

    @property
    def nonblocking(self):
        """Expose non-blocking interface via a file-like interface."""
        return self.NonblockingMethods(
            close=self.close_nonblocking,
            read=self.read_nonblocking,
            readline=self.readline_nonblocking,
            write=self.write_nonblocking,
        )

    def close_nonblocking(self):
        self._closed = True
        # NOTE: Call ``unblock`` here, not ``unblock_forever``, because
        # there may still be data to raed.
        self._gate.unblock()

    def read_nonblocking(self, size=-1):
        data = self._buffer.getvalue()
        if not data:
            if self._closed:
                return data
            else:
                return None

        if size < 0:
            size = len(data)

        if size == 0:
            data = self._data_type()
        elif size >= len(data):
            self._buffer = self._buffer_type()
        else:
            self._buffer = self._make_buffer(data[size:])
            data = data[:size]

        return data

    def readline_nonblocking(self, size=-1):
        data = self._buffer.getvalue()
        if not data:
            if self._closed:
                return data
            else:
                return None

        pos = data.find(self._newline)
        if pos < 0 and size < 0:
            if self._closed:
                size = len(data)
            else:
                return None
        elif size < 0 <= pos:
            size = pos + len(self._newline)
        elif pos < 0 <= size:
            pass  # Nothing here.
        else:
            # pos >= 0 and size >= 0.
            size = min(size, pos + len(self._newline))

        if size == 0:
            data = self._data_type()
        elif size >= len(data):
            self._buffer = self._buffer_type()
        else:
            self._buffer = self._make_buffer(data[size:])
            data = data[:size]

        return data

    def write_nonblocking(self, data):
        ASSERT.false(self._closed)
        self._gate.unblock()
        return self._buffer.write(data)


class BytesStream(StreamBase):

    def __init__(self):
        super().__init__(io.BytesIO, bytes, b'\n')


class StringStream(StreamBase):

    def __init__(self):
        # TODO: Handle all corner cases of newline characters (for now
        # it is fixed to '\n').
        super().__init__(io.StringIO, str, '\n')
