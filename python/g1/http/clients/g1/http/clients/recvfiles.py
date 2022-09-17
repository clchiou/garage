__all__ = [
    'recvfile',
]

import contextlib
import http.client
import logging
import re
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
                # read them, and then err out.  Maybe recvfile should
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

    _CRLF_PATTERN = re.compile(br'\r\n')

    def __init__(self):
        self.eof = False
        self._chunk_remaining = -2
        # Buffer for residual chunk size data from the last `_decode`.
        # It is fairly small for now because we do not expect big chunk
        # parameter.
        self._buffer = memoryview(bytearray(64))
        self._pos = 0

    def decode(self, pieces):
        ASSERT.false(self.eof)
        output = []
        for data in pieces:
            if data:
                self._decode(data, output)
        return output

    def _decode(self, data, output):

        def move(n):
            """Move ``n`` bytes from ``data`` to ``output``."""
            nonlocal data
            ASSERT.greater_or_equal(self._chunk_remaining, n)
            output.append(data[:n])
            data = data[n:]
            self._chunk_remaining -= n

        def expect(pattern):
            """Drop ``pattern`` prefix from ``data``."""
            nonlocal data
            n = min(len(pattern), len(data))
            ASSERT.equal(pattern[:n], data[:n])
            data = data[n:]
            return n

        while data:
            if self._chunk_remaining > 0:
                move(min(self._chunk_remaining, len(data)))
                continue

            if self._chunk_remaining == 0:
                self._chunk_remaining -= expect(b'\r\n')
                continue

            if self._chunk_remaining == -1:
                self._chunk_remaining -= expect(b'\n')
                continue

            match = self._CRLF_PATTERN.search(data)
            if not match:
                self._append(data)
                match = self._CRLF_PATTERN.search(self._buffer[:self._pos])
                if not match:
                    break
                data = self._reset()

            chunk_size = data[:match.start()]
            if self._pos > 0:
                self._append(chunk_size)
                chunk_size = self._reset()
            # TODO: Handle parameters (stuff after ';').
            chunk_size = int(
                bytes(chunk_size).split(b';', maxsplit=1)[0],
                base=16,
            )
            if chunk_size == 0:
                # TODO: Handle trailers.
                self.eof = True
            else:
                ASSERT.false(self.eof)

            data = data[match.end():]
            self._chunk_remaining = chunk_size

        if self.eof:
            ASSERT.empty(data)

    def _append(self, data):
        end = ASSERT.less_or_equal(self._pos + len(data), len(self._buffer))
        self._buffer[self._pos:end] = data
        self._pos = end

    def _reset(self):
        data = self._buffer[:self._pos]
        self._pos = 0
        return data

    def flush(self):
        ASSERT.true(self.eof)
        ASSERT.equal(self._chunk_remaining, -2)
        return []


class ContentDecoder:

    def __init__(self, urllib3_decoder):
        self._decoder = urllib3_decoder

    def decode(self, pieces):
        return [self._decoder.decompress(data) for data in pieces if data]

    def flush(self):
        return [self._decoder.flush()]
