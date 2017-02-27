"""HTTP request handlers."""

__all__ = [
    'ClientError',
    'Endpoint',
]

import logging

import http2


LOG = logging.getLogger(__name__)


class ClientError(Exception):
    """Represent HTTP 4xx status code."""

    def __init__(self, status, *,
                 headers=None,
                 message='',
                 internal_message=''):
        assert 400 <= status < 500
        super().__init__(internal_message or message)
        self.status = status
        self.headers = headers
        self.message = message.encode('utf8')

    def as_response(self):
        return http2.Response(
            status=self.status, headers=self.headers, body=self.message)


class Endpoint:
    """Request handler container for implementing API endpoint."""

    def __init__(self, endpoint, *,
                 decode=lambda headers, data: data,
                 encode=lambda headers, data: data,
                 make_response_headers=lambda request_headers: ()):
        self.endpoint = endpoint
        self.decode = decode
        self.encode = encode
        self.make_response_headers = make_response_headers

    async def __call__(self, stream):
        try:
            request = stream.request
            input = self.decode(request.headers, request.body)
            output = self.encode(request.headers, await self.endpoint(input))
            headers = [(b'content-length', b'%d' % len(output))]
            headers.extend(self.make_response_headers(request.headers))
            response = http2.Response(headers=headers, body=output)
        except ClientError as exc:
            LOG.warning('endpoint rejects request due to %s: %s',
                        exc, self.endpoint, exc_info=True)
            await stream.submit_response(exc.as_response())
        except Exception:
            LOG.exception('endpoint errs: %s', self.endpoint)
            await stream.submit_response(
                http2.Response(status=http2.Status.INTERNAL_SERVER_ERROR))
        else:
            await stream.submit_response(response)
