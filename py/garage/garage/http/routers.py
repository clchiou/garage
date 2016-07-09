"""HTTP request routing schemes."""

__all__ = [
    'HttpMethod',
    # Routers
    'ApiRouter',
    'PrefixRouter',
]

import enum
import logging
import re
from collections import OrderedDict
from http import HTTPStatus

from garage import asserts
from http2 import HttpError


LOG = logging.getLogger(__name__)


class HttpMethod(enum.Enum):
    GET = b'GET'
    HEAD = b'HEAD'
    POST = b'POST'
    PUT = b'PUT'


__all__.extend(HttpMethod.__members__.keys())
globals().update(HttpMethod.__members__)


class ApiRouter:
    """Simple routing scheme for implementing versioned API."""

    class ApiRouterError(Exception):
        pass

    class EndpointNotFound(ApiRouterError):
        pass

    class VersionNotSupported(ApiRouterError):
        pass

    def __init__(self, name, version):
        LOG.info('create service %s version %d', name, version)
        self.name = name
        self.version = version
        self._root_path = None
        self.handlers = {}

    @property
    def root_path(self):
        return self._root_path.decode('ascii')

    @root_path.setter
    def root_path(self, root_path):
        if isinstance(root_path, str):
            root_path = root_path.encode('ascii')
        self._root_path = root_path

    def add_handler(self, name, handler):
        LOG.info('%s/%d: add handler %s', self.name, self.version, name)
        name = name.encode('ascii')
        asserts.precond(name not in self.handlers)
        self.handlers[name] = handler

    async def __call__(self, request, response):
        path = request.headers.get(b':path')
        if path is None:
            raise HttpError(HTTPStatus.BAD_REQUEST)

        try:
            handler = self.dispatch(path)
        except self.EndpointNotFound:
            raise HttpError(HTTPStatus.NOT_FOUND) from None
        except self.VersionNotSupported as e:
            # Returning 400 when a request's version is newer is weird,
            # but none of other 4xx or 5xx code makes more sense anyway.
            # Like, 403?  But, could we say we understand a request of
            # newer version (premise of a 403)?  At least when returning
            # 400, we are telling the client that he could modify the
            # request (down-version it) and send it again.
            raise HttpError(HTTPStatus.BAD_REQUEST) from None

        await handler(request, response)

    PATTERN_ENDPOINT = re.compile(br'/(\d+)/([\w_\-.]+)')

    def dispatch(self, path):
        if self._root_path:
            if not path.startswith(self._root_path):
                raise self.EndpointNotFound(path)
            path = path[len(self._root_path):]

        match = self.PATTERN_ENDPOINT.match(path)
        if not match:
            raise self.EndpointNotFound(path)
        version = int(match.group(1))
        handler_name = match.group(2)

        handler = self.handlers.get(handler_name)
        if handler is None:
            raise self.EndpointNotFound(path)

        if self.version < version:
            raise self.VersionNotSupported(version)

        return handler


class PrefixRouter:
    """Routing based on HTTP request method and path prefix."""

    def __init__(self, *, name=None):
        self.name = name or self.__class__.__name__
        # prefix -> method -> handler
        self.handlers = OrderedDict()

    def add_handler(self, method, prefix, handler):
        asserts.precond(method in HttpMethod)
        if isinstance(prefix, str):
            prefix = prefix.encode('ascii')
        if prefix not in self.handlers:
            self.handlers[prefix] = {}
        handlers = self.handlers[prefix]
        asserts.precond(method.value not in handlers)  # No overwrite.
        handlers[method.value] = handler

    async def __call__(self, request, response):
        path = request.headers.get(b':path')
        if path is None:
            raise HttpError(HTTPStatus.BAD_REQUEST)
        for prefix, handlers in self.handlers.items():
            if path.startswith(prefix):
                break
        else:
            LOG.warning('%s: no matching path prefix: %r', self.name, path)
            raise HttpError(HTTPStatus.NOT_FOUND)

        method = request.headers.get(b':method')
        handler = handlers.get(method)
        if not handler:
            raise HttpError(
                HTTPStatus.METHOD_NOT_ALLOWED,
                headers={b'allow': b', '.join(sorted(handlers))},
            )

        await handler(request, response)
