__all__ = [
    'recvfile',
]

import contextlib
import enum
import http.client
import logging
import socket

from g1.asyncs.bases import adapters
from g1.bases import loggings
from g1.bases import pools
from g1.bases.assertions import ASSERT

LOG = logging.getLogger(__name__)

_CHUNK_SIZE = 8192
_BUFFER_POOL = pools.TimeoutPool(
    pool_size=128,
    allocate=lambda: bytearray(_CHUNK_SIZE),
    release=lambda _: None,
)


async def recvfile(response, file):
    """Receive response body into a file.

    The caller must set ``stream`` to true when make the request.

    DANGER! This breaks the multiple levels of encapsulation, from
    requests.Response all the way down to http.client.HTTPResponse.
    As a result, the response object is most likely unusable after a
    recvfile call, and you should probably close it immediately.
    """
    # requests sets _content to False initially.
    ASSERT.is_(response._content, False)
    ASSERT.false(response._content_consumed)

    urllib3_response = ASSERT.not_none(response.raw)
    chunked = urllib3_response.chunked

    httplib_response = ASSERT.isinstance(
        urllib3_response._fp, http.client.HTTPResponse
    )
    ASSERT.false(httplib_response.closed)
    sock = ASSERT.isinstance(httplib_response.fp.raw._sock, socket.socket)

    output = DecoderChain(file)

    if chunked:
        chunk_decoder = ChunkDecoder()
        output.add(chunk_decoder)
        num_to_read = 0
        eof = lambda: chunk_decoder.eof
    else:
        num_to_read = ASSERT.greater(
            ASSERT.not_none(httplib_response.length), 0
        )
        eof = lambda: num_to_read <= 0

    # Use urllib3's decoder code.
    urllib3_response._init_decoder()
    if urllib3_response._decoder is not None:
        output.add(ContentDecoder(urllib3_response._decoder))

    with contextlib.ExitStack() as stack:
        src = adapters.FileAdapter(httplib_response.fp)
        stack.callback(src.disown)

        sock.setblocking(False)
        stack.callback(sock.setblocking, True)

        buffer = memoryview(stack.enter_context(_BUFFER_POOL.using()))
        while not eof():
            if chunked:
                # TODO: If server sends more data at the end, like
                # response of the next request, for now recvfile might
                # read them and then ignore them.  Maybe recvfile should
                # check this, and not read more than it should instead?
                num_read = await src.readinto1(buffer)
            else:
                num_read = await src.readinto1(
                    buffer[:min(num_to_read, _CHUNK_SIZE)]
                )
            if num_read == 0:
                break
            output.write(buffer[:num_read])
            num_to_read -= num_read

        output.flush()

    # Sanity check.
    if not chunked:
        ASSERT.equal(num_to_read, 0)

    # Trick requests to release the connection back to the connection
    # pool, rather than closing/discarding it.
    response._content_consumed = True
    # http.client.HTTPConnection tracks the last response; so you have
    # to close it to make the connection object useable again.
    httplib_response.close()

    # Close the response for the caller since response is not useable
    # after recvfile.
    response.close()

    if loggings.ONCE_PER.check(1000):
        LOG.info('buffer pool stats: %r', _BUFFER_POOL.get_stats())


class DecoderChain:

    def __init__(self, file):
        self._file = file
        self._decoders = []

    def add(self, decoder):
        self._decoders.append(decoder)

    def write(self, data):
        pieces = [data]
        for decoder in self._decoders:
            pieces = decoder.decode(pieces)
        self._write(pieces)

    def flush(self):
        for i, decoder in enumerate(self._decoders):
            pieces = decoder.flush()
            for d in self._decoders[i + 1:]:
                pieces = d.decode(pieces)
            self._write(pieces)

    def _write(self, pieces):
        for data in pieces:
            if data:
                self._file.write(data)


class ChunkDecoder:

    class _States(enum.Enum):
        CHUNK_SIZE = enum.auto()
        CHUNK_EXTENSION = enum.auto()
        CHUNK_HEADER_LF = enum.auto()
        CHUNK_DATA = enum.auto()
        CHUNK_DATA_CR = enum.auto()
        CHUNK_DATA_LF = enum.auto()
        TRAILER_SECTION = enum.auto()
        TRAILER_SECTION_LF = enum.auto()
        END = enum.auto()

    _SEMICOLON = ord(b';')
    _CR = ord(b'\r')
    _LF = ord(b'\n')

    def __init__(self):
        self._state = self._States.CHUNK_SIZE
        self._buffer = memoryview(bytearray(16))
        self._buffer_size = 0
        self._chunk_remaining = 0

    @property
    def eof(self):
        return self._state is self._States.END

    def decode(self, pieces):
        ASSERT.is_not(self._state, self._States.END)
        output = []
        for data in pieces:
            if data:
                self._decode(data, output)
        return output

    def _decode(self, data, output):
        # pylint: disable=too-many-statements

        def find(*values):
            for i, b in enumerate(data):
                if b in values:
                    return i
            return -1

        while data:
            if self._state is self._States.CHUNK_SIZE:
                i = find(self._SEMICOLON, self._CR)
                if i == -1:
                    self._append_chunk_size_buffer(data)
                    break
                self._append_chunk_size_buffer(data[:i])
                if data[i] == self._SEMICOLON:
                    self._state = self._States.CHUNK_EXTENSION
                else:
                    self._state = self._States.CHUNK_HEADER_LF
                data = data[i + 1:]

            elif self._state is self._States.CHUNK_EXTENSION:
                i = find(self._CR)
                if i == -1:
                    break
                self._state = self._States.CHUNK_HEADER_LF
                data = data[i + 1:]

            elif self._state is self._States.CHUNK_HEADER_LF:
                ASSERT.equal(data[0], self._LF)
                self._chunk_remaining = self._parse_chunk_size()
                if self._chunk_remaining == 0:
                    self._state = self._States.TRAILER_SECTION
                else:
                    self._state = self._States.CHUNK_DATA
                data = data[1:]

            elif self._state is self._States.CHUNK_DATA:
                if self._chunk_remaining > len(data):
                    output.append(data)
                    self._chunk_remaining -= len(data)
                    break
                self._state = self._States.CHUNK_DATA_CR
                output.append(data[:self._chunk_remaining])
                data = data[self._chunk_remaining:]
                self._chunk_remaining = 0

            elif self._state is self._States.CHUNK_DATA_CR:
                ASSERT.equal(data[0], self._CR)
                self._state = self._States.CHUNK_DATA_LF
                data = data[1:]

            elif self._state is self._States.CHUNK_DATA_LF:
                ASSERT.equal(data[0], self._LF)
                self._state = self._States.CHUNK_SIZE
                data = data[1:]

            elif self._state is self._States.TRAILER_SECTION:
                i = find(self._CR)
                if i == -1:
                    # Re-use _chunk_remaining to track the length of the
                    # field line.
                    self._chunk_remaining += len(data)
                    break
                self._state = self._States.TRAILER_SECTION_LF
                self._chunk_remaining += i
                data = data[i + 1:]

            elif self._state is self._States.TRAILER_SECTION_LF:
                ASSERT.equal(data[0], self._LF)
                if self._chunk_remaining == 0:
                    self._state = self._States.END
                else:
                    self._state = self._States.TRAILER_SECTION
                self._chunk_remaining = 0
                data = data[1:]

            else:
                ASSERT.is_(self._state, self._States.END)
                LOG.warning(
                    'data after the end: len(data)=%d data[:64]=%r',
                    len(data),
                    bytes(data[:64]),
                )
                break

    def _append_chunk_size_buffer(self, data):
        new_size = ASSERT.less_or_equal(
            self._buffer_size + len(data),
            len(self._buffer),
        )
        self._buffer[self._buffer_size:new_size] = data
        self._buffer_size = new_size

    def _parse_chunk_size(self):
        chunk_size = int(
            bytes(self._buffer[:self._buffer_size]),
            base=16,
        )
        self._buffer_size = 0
        return chunk_size

    def flush(self):
        # Allow calling flush when TRAILER_SECTION because some sites do
        # not send the last CRLF.
        ASSERT.in_(
            self._state,
            (self._States.TRAILER_SECTION, self._States.END),
        )
        return []


class ContentDecoder:

    def __init__(self, urllib3_decoder):
        self._decoder = urllib3_decoder

    def decode(self, pieces):
        return [self._decoder.decompress(data) for data in pieces if data]

    def flush(self):
        return [self._decoder.flush()]
