"""Utilities for datetime objects."""

__all__ = [
    'parse_isoformat',
]

from datetime import datetime


# ISO 8601 date and time format (with time zone designator).
DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%f%z'
DATETIME_FORMAT_WO_TIMEZONE = '%Y-%m-%dT%H:%M:%S.%f'


def parse_isoformat(dt_str):
    for dt_format in (DATETIME_FORMAT, DATETIME_FORMAT_WO_TIMEZONE):
        try:
            return datetime.strptime(dt_str, dt_format)
        except ValueError:
            pass
    raise ValueError('not ISO-8601 format: %r' % dt_str)
