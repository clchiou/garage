"""Simple time zone utilities."""

__all__ = [
    'TimeZone',
]

import datetime
import enum


ZERO = datetime.timedelta(0)


class TimeZone(datetime.tzinfo, enum.Enum):

    CST = (datetime.timedelta(hours=8), 'China Standard Time')
    UTC = (ZERO, 'Coordinated Universal Time')

    def __init__(self, utcoffset, tzname):
        self._utcoffset = utcoffset
        self._tzname = tzname

    def utcoffset(self, _):
        return self._utcoffset

    def tzname(self, _):
        return self._tzname

    def dst(self, _):
        return ZERO
