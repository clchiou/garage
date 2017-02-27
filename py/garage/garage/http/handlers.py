"""HTTP request handlers."""

__all__ = [
    'ApiEndpointHandler',
]

import http2


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
