__all__ = [
    'BufferHandler',
    'DirHandler',
    'FileHandler',
    'make_buffer_handler',
    'make_dir_handler',
    'make_file_handler',
    # Context.
    'LOCAL_PATH',
]

import mimetypes

from g1.bases import labels

from .. import consts
from .. import wsgi_apps

from . import composers
from . import etags


def make_dir_handler(local_dir_path):
    dir_handler = DirHandler(local_dir_path)
    return composers.Chain([
        dir_handler.check,
        composers.MethodRouter({
            consts.METHOD_HEAD: dir_handler.head,
            consts.METHOD_GET: dir_handler.get,
        }),
    ])


def make_file_handler(local_file_path, headers=()):
    file_handler = FileHandler(local_file_path, headers=headers)
    return composers.Chain([
        composers.MethodRouter({
            consts.METHOD_HEAD: file_handler.head,
            consts.METHOD_GET: file_handler.get,
        }),
    ])


def make_buffer_handler(filename, content, headers=()):
    buffer_handler = BufferHandler(filename, content, headers=headers)
    return composers.Chain([
        composers.MethodRouter({
            consts.METHOD_HEAD: buffer_handler.head,
            consts.METHOD_GET: buffer_handler.get,
        }),
    ])


def get_local_path(request, local_dir_path):
    path_str = composers.get_path_str(request)
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
        # We don't want this to be a generic dir handler, and so we do
        # not handle directories.
        raise wsgi_apps.HttpError(
            consts.Statuses.NOT_FOUND, 'not a file: %s' % local_path
        )
    return local_path


_CONTENT_TYPE_FIXES = {
    # Although RFC4329 obsoletes text/javascript and recommends
    # application/javascript (and the stdlib correctly implements the
    # RFC), the HTML spec still chooses text/javascript (for
    # compatibility reason).  For more details:
    # https://html.spec.whatwg.org/multipage/infrastructure.html#dependencies
    'application/javascript': 'text/javascript',
}


def guess_content_type(filename):
    content_type, file_encoding = mimetypes.guess_type(filename)
    if content_type:
        fixed_type = _CONTENT_TYPE_FIXES.get(content_type)
        if fixed_type is not None:
            content_type = fixed_type
        if file_encoding:
            content_type = '%s+%s' % (content_type, file_encoding)
    else:
        if file_encoding:
            content_type = 'application/x-' + file_encoding
        else:
            content_type = 'application/octet-stream'
    return content_type


LOCAL_PATH = labels.Label(__name__, 'local_path')


class DirHandler:
    """Serve files under the given directory."""

    def __init__(self, local_dir_path):
        if not mimetypes.inited:
            mimetypes.init()
        self._local_dir_path = local_dir_path.resolve()

    async def check(self, request, response):
        """Check whether request path is under the given directory.

        Use this to pre-check for DirHandler when it is wrapped deeply
        inside other handlers.
        """
        del response  # Unused.
        request.context.set(
            LOCAL_PATH, get_local_path(request, self._local_dir_path)
        )

    def _prepare(self, request, response):
        local_path = request.context.get(LOCAL_PATH)
        if local_path is None:
            local_path = get_local_path(request, self._local_dir_path)
        content = local_path.read_bytes()
        response.status = consts.Statuses.OK
        response.headers.update({
            consts.HEADER_CONTENT_TYPE:
            guess_content_type(local_path.name),
            consts.HEADER_CONTENT_LENGTH:
            str(len(content)),
            consts.HEADER_ETAG:
            etags.compute_etag(content),
        })
        etags.maybe_raise_304(request, response)
        return content

    async def head(self, request, response):
        self._prepare(request, response)

    async def get(self, request, response):
        content = self._prepare(request, response)
        await response.write(content)

    __call__ = get


class BufferHandler:
    """Serve a buffer as a file."""

    def __init__(self, filename, content, headers=()):
        if not mimetypes.inited:
            mimetypes.init()
        self._content = content
        self._headers = {
            consts.HEADER_CONTENT_TYPE: guess_content_type(filename),
            consts.HEADER_CONTENT_LENGTH: str(len(self._content)),
            consts.HEADER_ETAG: etags.compute_etag(self._content),
        }
        self._headers.update(headers)

    async def head(self, request, response):
        response.status = consts.Statuses.OK
        response.headers.update(self._headers)
        etags.maybe_raise_304(request, response)

    async def get(self, request, response):
        await self.head(request, response)
        await response.write(self._content)

    __call__ = get


class FileHandler(BufferHandler):
    """Serve a (small) file."""

    def __init__(self, local_file_path, headers=()):
        super().__init__(
            local_file_path.name,
            local_file_path.read_bytes(),
            headers=headers,
        )
