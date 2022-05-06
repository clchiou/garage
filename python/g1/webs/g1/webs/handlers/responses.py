"""Handlers that modify responses."""

__all__ = [
    'Defaults',
    'ErrorDefaults',
]

import datetime

from g1.bases import datetimes
from g1.bases.assertions import ASSERT

from .. import consts
from .. import wsgi_apps

RFC_7231_FORMAT = (
    '{day_name}, {day:02d} {month} {year:04d} '
    '{hour:02d}:{minute:02d}:{second:02d} '
    # Although RFC 5322 suggests using "+0000" rather than "GMT" (which
    # is obsolete), RFC 7231 and most web sites that I checked seem to
    # be still using "GMT".
    'GMT'
)

RFC_7231_MONTHS = (
    'Jan', 'Feb', 'Mar', \
    'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep',
    'Oct', 'Nov', 'Dec',
)

RFC_7231_DAY_NAMES = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')


# NOTE: Generally you should place this before the application handler
# so that the application handler may access these defaults (say, it may
# copy the defaults to the exception object when raising 304).
class Defaults:

    def __init__(self, headers, *, auto_date=True):
        self._headers = headers
        self._auto_date = auto_date

    async def __call__(self, request, response):
        del request  # Unused.
        _setdefaults(response.headers, self._headers)
        if consts.HEADER_DATE not in response.headers and self._auto_date:
            response.headers[consts.HEADER_DATE] = rfc_7231_date()


class ErrorDefaults:

    def __init__(
        self,
        handler,
        error_headers,
        error_contents=None,  # status-to-content dict.
        *,
        auto_date=True,
    ):
        self._handler = handler
        self._error_headers = error_headers
        self._error_contents = (
            error_contents if error_contents is not None else {}
        )
        self._auto_date = auto_date

    async def __call__(self, request, response):
        try:
            return await self._handler(request, response)
        except wsgi_apps.HttpError as exc:
            _setdefaults(exc.headers, self._error_headers)
            if consts.HEADER_DATE not in exc.headers and self._auto_date:
                exc.headers[consts.HEADER_DATE] = rfc_7231_date()
            if not exc.content:
                exc.content = self._error_contents.get(exc.status, exc.content)
            raise


def _setdefaults(headers, pairs):
    for header, value in pairs:
        headers.setdefault(header, value)


def rfc_7231_date(now=None):
    if not now:
        now = datetimes.utcnow()
    # We can't handle non-UTC time zone at the moment.
    ASSERT.is_(now.tzinfo, datetime.timezone.utc)
    return RFC_7231_FORMAT.format(
        year=now.year,
        month=RFC_7231_MONTHS[now.month - 1],
        day_name=RFC_7231_DAY_NAMES[now.weekday()],
        day=now.day,
        hour=now.hour,
        minute=now.minute,
        second=now.second,
    )
