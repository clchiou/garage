__all__ = [
    'compute_etag',
    'compute_etag_from_file',
    'maybe_raise_304',
]

import hashlib
import logging
import re

from .. import consts
from .. import wsgi_apps

LOG = logging.getLogger(__name__)

_CHUNK_SIZE = 8192


def compute_etag(content):
    hasher = hashlib.md5()
    hasher.update(content)
    return '"%s"' % hasher.hexdigest()


def compute_etag_from_file(content_file):
    hasher = hashlib.md5()
    buffer = memoryview(bytearray(_CHUNK_SIZE))
    while True:
        num_read = content_file.readinto(buffer)
        if num_read <= 0:
            break
        hasher.update(buffer[:num_read])
    return '"%s"' % hasher.hexdigest()


def maybe_raise_304(request, response):
    """Check If-None-Match with ETag and maybe raise 304."""
    if request.method not in (consts.METHOD_HEAD, consts.METHOD_GET):
        LOG.warning(
            'check If-None-Match in non-standard request method: %s %s',
            request.method,
            request.path_str,
        )
    if_none_match = request.get_header(consts.HEADER_IF_NONE_MATCH)
    if if_none_match is None:
        return
    etag = response.headers.get(consts.HEADER_ETAG)
    if etag is None:
        return
    # TODO: Handle W/"..." weak validator.
    if etag in _parse_etags(if_none_match):
        raise wsgi_apps.HttpError(
            consts.Statuses.NOT_MODIFIED,
            'etag matches: %s vs %s' % (etag, if_none_match),
            response.headers,
        )


_ETAGS_PATTERN = re.compile(r'((?:W/)?"[^"]+")(?:\s*,\s*)?')


def _parse_etags(etags_str):
    if etags_str.strip() == '*':
        return _MatchAll()
    return frozenset(
        match.group(1) for match in _ETAGS_PATTERN.finditer(etags_str)
    )


class _MatchAll:

    def __contains__(self, _):
        return True
