"""Handlers that modify responses."""

__all__ = [
    'Defaults',
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


class Defaults:

    def __init__(
        self,
        handler,
        headers=(),
        error_headers=None,
        error_contents=None,  # status-to-content dict.
        *,
        auto_date=True,
    ):
        self._handler = handler
        self._headers = headers
        self._error_headers = (
            error_headers if error_headers is not None else headers
        )
        self._error_contents = (
            error_contents if error_contents is not None else {}
        )
        self._auto_date = auto_date

    async def __call__(self, request, response):
        try:
            result = await self._handler(request, response)
            _setdefaults(response.headers, self._headers)
            if consts.HEADER_DATE not in response.headers and self._auto_date:
                response.headers[consts.HEADER_DATE] = rfc_7231_date()
            return result
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
