"""In-memory streams."""

__all__ = [
    'BytesStream',
    'StringStream',
]

import collections
import io

from g1.bases import classes
from g1.bases.assertions import ASSERT

from . import locks


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

    __repr__ = classes.make_repr(
        '{state}',
        state=lambda self: 'closed' if self._closed else 'open',
    )

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
            close=self.close,
            read=self.read_nonblocking,
            readline=self.readline_nonblocking,
            write=self.write_nonblocking,
        )

    def close(self):
        self._closed = True
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
