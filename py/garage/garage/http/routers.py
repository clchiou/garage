"""HTTP request routers."""

__all__ = [
    'ApiRouter',
    'PrefixRouter',
]

import logging
import re
from collections import OrderedDict

import http2

from garage import asserts
from garage.http.servers import ClientError


LOG = logging.getLogger(__name__)


class ApiRouter:
    """Simple routing scheme for implementing versioned API."""

    class ApiRouterError(Exception):
        pass

    class EndpointNotFound(ApiRouterError):
        pass

    class VersionNotSupported(ApiRouterError):
        pass

    def __init__(self, name, version):
        self.name = name
        self.version = version
        self._root_path = None
        self.handlers = {}

    def __repr__(self):
        args = (
            __name__, self.__class__.__qualname__,
            self.name, self.version, self._root_path,
            id(self),
        )
        return '<%s.%s<name=%r, version=%r, root_path=%r> at 0x%x>' % args

    @property
    def root_path(self):
        return self._root_path.decode('ascii') if self._root_path else None

    @root_path.setter
    def root_path(self, root_path):
        if isinstance(root_path, str):
            root_path = root_path.encode('ascii')
        self._root_path = root_path

    def add_handler(self, name, handler):
        LOG.info('%s/%d: add handler %r', self.name, self.version, name)
        name = name.encode('ascii')
        asserts.not_in(name, self.handlers)
        self.handlers[name] = handler

    async def __call__(self, stream):
        path = stream.request.path
        if not path:
            raise ClientError(
                http2.Status.BAD_REQUEST,
                internal_message='empty path',
            )

        try:
            handler = self.route(path)
        except self.EndpointNotFound:
            raise ClientError(
                http2.Status.NOT_FOUND,
                internal_message='no endpoint found: %s' % path,
            )
        except self.VersionNotSupported:
            # Returning 400 when a request's version is newer is weird,
            # but none of other 4xx or 5xx code makes more sense anyway.
            # Like, 403?  But, could we say we understand a request of
            # newer version (premise of a 403)?  At least when returning
            # 400, we are telling the client that he could modify the
            # request (down-version it) and send it again.
            raise ClientError(
                http2.Status.BAD_REQUEST,
                internal_message='version is not supported: %s' % path,
            )

        await handler(stream)

    PATTERN_ENDPOINT = re.compile(br'/(\d+)/([\w_\-.]+)')

    def route(self, path):
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

    def __init__(self):
        # prefix -> method -> handler
        self.handlers = OrderedDict()

    def add_handler(self, method, prefix, handler):
        if isinstance(method, str):
            method = method.encode('ascii')
        if method not in http2.Method:
            method = http2.Method(method)
        LOG.info('%s: add handler: %s %r',
                 self.__class__.__name__, method.name, prefix)
        if isinstance(prefix, str):
            prefix = prefix.encode('ascii')
        asserts.precond(
            all(not prefix.startswith(p) or prefix == p
                for p in self.handlers),
            'prefix %r is hidden by one of the handler prefixes: %r',
            prefix, self.handlers.keys()
        )
        if prefix not in self.handlers:
            self.handlers[prefix] = {}
        handlers = self.handlers[prefix]
        asserts.not_in(method, handlers)  # No overwrite
        handlers[method] = handler

    async def __call__(self, stream):
        if not stream.request.method:
            raise ClientError(
                http2.Status.BAD_REQUEST,
                internal_message='empty method',
            )
        if not stream.request.path:
            raise ClientError(
                http2.Status.BAD_REQUEST,
                internal_message='empty path',
            )
        handler = self.route(stream.request.method, stream.request.path)
        await handler(stream)

    def route(self, method, path):
        try:
            method = http2.Method(method)
        except ValueError:
            raise ClientError(
                http2.Status.BAD_REQUEST,
                internal_message='incorrect method: %s' % method,
            )

        for prefix, handlers in self.handlers.items():
            if path.startswith(prefix):
                break
        else:
            raise ClientError(
                http2.Status.NOT_FOUND,
                internal_message='no match path prefix: %s' % path,
            )

        try:
            return handlers[method]
        except KeyError:
            allow = b', '.join(sorted(method.value for method in handlers))
            raise ClientError(
                http2.Status.METHOD_NOT_ALLOWED,
                headers=[(b'allow', allow)],
                internal_message='method not allowed: %s' % method,
            )
