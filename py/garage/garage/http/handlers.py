"""Helpers for constructing HTTP request handlers."""

__all__ = [
    'ApiHandler',
    'Handler',
]

import logging
from http import HTTPStatus

from garage.asyncs.futures import all_of
from http2 import HttpError


LOG = logging.getLogger(__name__)


class Handler:
    """Generic handler container."""

    def __init__(self, handler):
        self.handler = handler
        self.policies = []
        self.timeout = None

    def add_policy(self, policy):
        self.policies.append(policy)

    async def __call__(self, request, response):
        try:
            if self.policies:
                await all_of(
                    [policy(request.headers) for policy in self.policies],
                    timeout=self.timeout,
                )
            await self.handler(request, response)
        except HttpError:
            raise
        except Exception:
            LOG.exception('handler err: %r', self.handler)
            raise HttpError(HTTPStatus.INTERNAL_SERVER_ERROR) from None


class ApiHandler(Handler):
    """Handler container for implementing API endpoint."""

    def __init__(self, endpoint):
        super().__init__(self.__handler)
        self.endpoint = endpoint
        self.decode = self.encode = lambda _, data: data
        # Rather that content_type, or should we introduce another kind
        # of policy that is applied on response headers?
        self.content_type = None

    async def __handler(self, request, response):
        output = self.encode(
            request.headers,
            await self.endpoint(
                self.decode(
                    request.headers,
                    await request.body,
                )
            ),
        )
        response.headers[b':status'] = b'200'
        response.headers[b'content-length'] = b'%d' % len(output)
        if self.content_type:
            response.headers[b'content-type'] = self.content_type
        await response.write(output)
        response.close()
