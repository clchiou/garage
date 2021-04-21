__all__ = [
    'recvfile',
]

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


async def recvfile(self, file):
    """Receive response body into a file.

    This is probably only useful for downloading big, non-encoded
    response data, like images.  The caller must set ``stream`` to true
    when make the request.

    NOTE:

    * DANGER! This breaks the multiple levels of encapsulation, from
      requests.Response all the way down to http.client.HTTPResponse.
      As a result, the response object is most likely unusable after a
      recvfile call, and you should probably close it immediately.

    * For now, no Content-Encoding nor Transfer-Encoding are supported.
    """
    # requests sets _content to False initially.
    ASSERT.is_(self._content, False)
    ASSERT.false(self._content_consumed)

    for header in ['Content-Encoding', 'Transfer-Encoding']:
        encoding = self.headers.get(header)
        if encoding:
            raise ValueError(
                '%s is not supported: %r %s' % (header, encoding, self.url)
            )

    urllib3_response = ASSERT.not_none(self.raw)
    ASSERT.false(urllib3_response.chunked)

    httplib_response = ASSERT.isinstance(
        urllib3_response._fp, http.client.HTTPResponse
    )
    ASSERT.false(httplib_response.closed)

    sock = ASSERT.isinstance(httplib_response.fp.raw._sock, socket.socket)
    num_to_read = ASSERT.greater(ASSERT.not_none(httplib_response.length), 0)

    src = adapters.FileAdapter(httplib_response.fp)
    try:
        sock.setblocking(False)

        with _BUFFER_POOL.using() as buffer:
            buffer = memoryview(buffer)
            while num_to_read > 0:
                num_read = await src.readinto1(
                    buffer[:min(num_to_read, _CHUNK_SIZE)]
                )
                if num_read == 0:
                    break
                file.write(buffer[:num_read])
                num_to_read -= num_read

        # Sanity check.
        ASSERT.equal(num_to_read, 0)

    finally:
        src.disown()
        sock.setblocking(True)

    # Trick requests to release the connection back to the connection
    # pool, rather than closing/discarding it.
    self._content_consumed = True
    # http.client.HTTPConnection tracks the last response; so you have
    # to close it to make the connection object useable again.
    httplib_response.close()

    loggings.ONCE_PER(
        1000, LOG.info, 'buffer pool stats: %r', _BUFFER_POOL.get_stats()
    )
