"""Handlers that compose handlers."""

__all__ = [
    'Chain',
    'MethodRouter',
    'PathPatternRouter',
    # Context.
    'PATH_MATCH',
]

import re

from g1.bases import labels
from g1.bases.assertions import ASSERT

from .. import consts
from .. import wsgi_apps


class Chain:
    """Chain a series of handlers."""

    def __init__(self, handlers):
        self._handlers = handlers

    async def __call__(self, request, response):
        for handler in self._handlers:
            await handler(request, response)


class MethodRouter:
    """Route to one of the handlers bases on request method.

    It takes a dict of handlers where the keys are HTTP methods.
    """

    def __init__(self, handlers, *, auto_options=True):
        # Make a copy before modifying it.
        self._handlers = ASSERT.not_empty(handlers).copy()
        if auto_options:
            self._handlers.setdefault(consts.METHOD_OPTIONS, self._options)
        self._allow = ', '.join(sorted(self._handlers))

    async def _options(self, request, response):
        del request  # Unused.
        response.status = consts.Statuses.NO_CONTENT
        response.headers[consts.HEADER_ALLOW] = self._allow

    async def __call__(self, request, response):
        handler = self._handlers.get(request.method)
        if not handler:
            raise wsgi_apps.HttpError(
                consts.Statuses.METHOD_NOT_ALLOWED,
                'unsupported request method: %s' % request.method,
                {consts.HEADER_ALLOW: self._allow},
            )
        return await handler(request, response)


PATH_MATCH = labels.Label(__name__, 'path_match')


class PathPatternRouter:
    """Route to one of the handlers bases on request path.

    It takes a list of pattern-handler pairs.  If you are also using
    groups in the patterns, you should use named groups "(?P<name>...)"
    because patterns are concatenated.
    """

    def __init__(self, handlers):
        ASSERT.not_empty(handlers)
        path_patterns = []
        self._handlers = {}
        for i, (pattern, handler) in enumerate(handlers):
            group_name = '_%s__%d' % (self.__class__.__name__, i)
            path_patterns.append('(?P<%s>%s)' % (group_name, pattern))
            self._handlers[group_name] = handler
        self._path_pattern = re.compile('|'.join(path_patterns))

    async def __call__(self, request, response):
        match = self._path_pattern.match(request.path_str)
        if not match:
            raise wsgi_apps.HttpError(
                consts.Statuses.NOT_FOUND,
                'path does not match any pattern: %s' % request.path_str,
            )
        ASSERT.setitem(request.context, PATH_MATCH, match)
        return await self._handlers[match.lastgroup](request, response)

    @staticmethod
    def group(request, *groups, default=None):
        match = request.context.get(PATH_MATCH)
        if not match:
            return default
        return match.group(*groups)

    @staticmethod
    def get_path_str(request):
        path_str = request.path_str
        match = request.context.get(PATH_MATCH)
        if match:
            path_str = path_str[match.end():]
        return path_str

    @classmethod
    def get_path(cls, request):
        return consts.UrlPath(cls.get_path_str(request))
