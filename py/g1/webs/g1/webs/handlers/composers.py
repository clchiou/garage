"""Handlers that compose handlers."""

__all__ = [
    'Chain',
    'MethodRouter',
    'PathPatternRouter',
    # Context.
    'PATH_MATCH',
    'get_path',
    'get_path_str',
    'group',
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


def group(request, *groups, default=None):
    match = request.context.get(PATH_MATCH)
    if match is None:
        return default
    return match.group(*groups)


def get_path_str(request):
    path_str = request.path_str
    match = request.context.get(PATH_MATCH)
    if match is not None:
        path_str = path_str[match.end():]
    return path_str


def get_path(request):
    return consts.UrlPath(get_path_str(request))


class PathPatternRouter:
    """Route to one of the handlers bases on request path.

    It takes a list of pattern-handler pairs, and matches request
    against them serially.
    """

    def __init__(self, handlers):
        ASSERT.not_empty(handlers)
        self._handlers = [(re.compile(p), h) for p, h in handlers]

    async def __call__(self, request, response):
        for regex, handler in self._handlers:
            match = regex.match(request.path_str)
            if match:
                request.context.set(PATH_MATCH, match)
                return await handler(request, response)
        raise wsgi_apps.HttpError(
            consts.Statuses.NOT_FOUND,
            'path does not match any pattern: %s' % request.path_str,
        )
