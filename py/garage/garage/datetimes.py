"""Utilities for datetime objects."""

__all__ = [
    'format_iso8601',
    'parse_iso8601',

    'utcfromtimestamp',
    'utcnow',
]

from datetime import datetime

from .timezones import TimeZone


# ISO 8601 date and time format (with time zone designator).
DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%f%z'
DATETIME_FORMAT_WO_TIMEZONE = '%Y-%m-%dT%H:%M:%S.%f'


def format_iso8601(dt_obj):
    # datetime.isoformat() would generate a ':' in the time zone, which
    # datetime.strptime cannot parse :(
    # So use datetime.strftime(DATETIME_FORMAT) here.
    return dt_obj.strftime(DATETIME_FORMAT)


def parse_iso8601(dt_str):
    for dt_format in (DATETIME_FORMAT, DATETIME_FORMAT_WO_TIMEZONE):
        try:
            return datetime.strptime(dt_str, dt_format)
        except ValueError:
            pass
    raise ValueError('not ISO-8601 format: %r' % dt_str)


def utcfromtimestamp(timestamp):
    return datetime.fromtimestamp(timestamp, TimeZone.UTC)


def utcnow():
    return datetime.utcnow().replace(tzinfo=TimeZone.UTC)
