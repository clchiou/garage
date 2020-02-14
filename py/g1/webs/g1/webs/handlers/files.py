__all__ = [
    'FileHandler',
    'PathChecker',
    'make_handler',
    # Context.
    'LOCAL_PATH',
]

import mimetypes

from g1.bases import labels
from g1.bases.assertions import ASSERT

from .. import consts
from .. import wsgi_apps

from . import composers


def make_handler(local_dir_path):
    file_handler = FileHandler(local_dir_path)
    return composers.Chain([
        PathChecker(local_dir_path),
        composers.MethodRouter({
            consts.METHOD_HEAD: file_handler.head,
            consts.METHOD_GET: file_handler.get,
        }),
    ])


def get_local_path(request, local_dir_path):
    path_str = composers.PathPatternRouter.get_path_str(request)
    # We use ``resolve`` to normalize path, which also follows symlinks.
    # A side effect is that this handler rejects any symlink to file
    # that is out of scope, which may be not bad.
    local_path = (local_dir_path / path_str.lstrip('/')).resolve()
    try:
        local_path.relative_to(local_dir_path)
    except ValueError:
        raise wsgi_apps.HttpError(
            consts.Statuses.NOT_FOUND,
            'out of scope: %s vs %s' % (local_path, local_dir_path),
        ) from None
    if not local_path.is_file():
        # We don't want this to be a generic file handler, and so we
        # do not handle directories.
        raise wsgi_apps.HttpError(
            consts.Statuses.NOT_FOUND, 'not a file: %s' % local_path
        )
    return local_path


def guess_content_type(filename):
    content_type, file_encoding = mimetypes.guess_type(filename)
    if content_type:
        if file_encoding:
            content_type = '%s+%s' % (content_type, file_encoding)
    else:
        if file_encoding:
            content_type = 'application/x-' + file_encoding
        else:
            content_type = 'application/octet-stream'
    return content_type


LOCAL_PATH = labels.Label(__name__, 'local_path')


class PathChecker:
    """Check whether request path is under the given directory.

    Use this to pre-check for FileHandler when it is wrapped deeply
    inside other handlers.
    """

    def __init__(self, local_dir_path):
        self._local_dir_path = local_dir_path.resolve()

    async def __call__(self, request, response):
        del response  # Unused.
        ASSERT.setitem(
            request.context,
            LOCAL_PATH,
            get_local_path(request, self._local_dir_path),
        )


class FileHandler:
    """Serve files under the given directory."""

    def __init__(self, local_dir_path):
        if not mimetypes.inited:
            mimetypes.init()
        self._local_dir_path = local_dir_path.resolve()

    def _prepare(self, request, response):
        local_path = request.context.get(LOCAL_PATH)
        if local_path is None:
            local_path = get_local_path(request, self._local_dir_path)
        response.status = consts.Statuses.OK
        response.headers.update({
            consts.HEADER_CONTENT_TYPE:
            guess_content_type(local_path.name),
            consts.HEADER_CONTENT_LENGTH:
            str(local_path.stat().st_size),
        })
        return local_path

    async def head(self, request, response):
        self._prepare(request, response)

    async def get(self, request, response):
        local_path = self._prepare(request, response)
        await response.write(local_path.read_bytes())

    __call__ = get
