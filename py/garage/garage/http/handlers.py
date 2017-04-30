"""HTTP request handlers."""

__all__ = [
    'ApiEndpointHandler',
    'UriPath',
    'add_date_to_headers',
    'parse_request',
]

from pathlib import PurePosixPath as UriPath
import datetime
import urllib.parse

import http2

from garage import asserts

from . import servers


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


def parse_request(request) -> urllib.parse.SplitResult:

    if not request.scheme:
        raise servers.ClientError(http2.Status.BAD_REQUEST)

    if not request.path:
        raise servers.ClientError(http2.Status.BAD_REQUEST)

    authority = request.authority
    if not authority:
        for header, value in request.headers:
            if header != b'Host':
                continue
            if authority:
                msg = 'duplicate "Host" header: %r, %r' % (authority, value)
                raise servers.ClientError(
                    http2.Status.BAD_REQUEST, internal_message=msg)
            authority = value
    if not authority:
        raise servers.ClientError(http2.Status.BAD_REQUEST)

    try:
        uri = b'%s://%s%s' % (request.scheme.value, authority, request.path)
        result = urllib.parse.urlsplit(uri.decode('ascii'))
        return result._replace(path=UriPath(result.path))
    except Exception as exc:
        raise servers.ClientError(http2.Status.BAD_REQUEST) from exc


def add_date_to_headers(headers):
    """Add 'Date' field to headers without checking its presence.

    This modifies headers *in place*.
    """
    headers.append((b'Date', _rfc_7231_date()))


RFC_7231_FORMAT = \
    '{day_name}, {day:02d} {month} {year:04d} {hour:02d}:{minute:02d}:{second:02d} GMT'
RFC_7231_MONTHS = (
    'Jan', 'Feb', 'Mar',
    'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep',
    'Oct', 'Nov', 'Dec',
)
RFC_7231_DAY_NAMES = (
    'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun',
)


def _rfc_7231_date(now=None):
    if not now:
        now = datetime.datetime.utcnow()
    # We can't handle non-UTC time zone at the moment.
    asserts.none(now.tzinfo)
    formatted = RFC_7231_FORMAT.format(
        year=now.year,
        month=RFC_7231_MONTHS[now.month - 1],
        day_name=RFC_7231_DAY_NAMES[now.weekday()],
        day=now.day,
        hour=now.hour,
        minute=now.minute,
        second=now.second,
    )
    return formatted.encode('ascii')
