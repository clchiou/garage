"""HTTP request handlers."""

__all__ = [
    'ApiEndpointHandler',
    'UriPath',
    'parse_request',
]

from pathlib import PurePosixPath as UriPath
import urllib.parse

import http2

from . import servers


class ApiEndpointHandler:
    """Request handler of an API endpoint."""

    def __init__(self, endpoint, *,
                 decode=lambda headers, data: data,
                 encode=lambda headers, data: data,
                 make_response_headers=lambda request_headers: ()):
        self.endpoint = endpoint
        self.decode = decode
        self.encode = encode
        self.make_response_headers = make_response_headers

    async def __call__(self, stream):
        request = stream.request
        input = self.decode(request.headers, request.body)
        output = self.encode(request.headers, await self.endpoint(input))
        headers = [(b'content-length', b'%d' % len(output))]
        headers.extend(self.make_response_headers(request.headers))
        await stream.submit_response(
            http2.Response(headers=headers, body=output))


def parse_request(request) -> urllib.parse.SplitResult:

    if not request.scheme:
        raise servers.ClientError(http2.Status.BAD_REQUEST)

    if not request.path:
        raise servers.ClientError(http2.Status.BAD_REQUEST)

    authority = request.authority
    if not authority:
        for header, value in request.headers:
            if header != b'Host':
                continue
            if authority:
                msg = 'duplicate "Host" header: %r, %r' % (authority, value)
                raise servers.ClientError(
                    http2.Status.BAD_REQUEST, internal_message=msg)
            authority = value
    if not authority:
        raise servers.ClientError(http2.Status.BAD_REQUEST)

    try:
        uri = b'%s://%s%s' % (request.scheme.value, authority, request.path)
        result = urllib.parse.urlsplit(uri.decode('ascii'))
        return result._replace(path=UriPath(result.path))
    except Exception as exc:
        raise servers.ClientError(http2.Status.BAD_REQUEST) from exc
