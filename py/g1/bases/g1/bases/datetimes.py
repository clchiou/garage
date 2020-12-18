"""Extension of standard library's datetime.

A common pitfall of using datetime to store a timestamps is not setting
timezone to UTC, which is then default to the local timezone.  This
produces wrong results when converting datetime-represented timestamp
to/from a number-represented timestamp.  Specifically, when the local
timezone is not UTC, ``datetime.fromtimestamp(0)`` does not return
1970-01-01, and ``datetime(1970, 1, 1).timestamp()`` does not return 0.
All timestamp helpers of this module will set timezone to UTC.
"""

__all__ = [
    'UNIX_EPOCH',
    'fromisoformat',
    'make_timestamp',
    'timestamp_date',
    'utcfromtimestamp',
    'utcnow',
]

import datetime


def fromisoformat(string):
    """Parse a timestamp with datetime.fromisoformat."""
    timestamp = datetime.datetime.fromisoformat(string)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=datetime.timezone.utc)
    else:
        return timestamp.astimezone(datetime.timezone.utc)


def make_timestamp(
    year, month, day, hour=0, minute=0, second=0, microsecond=0
):
    """Make a datetime-represented timestamp."""
    return datetime.datetime(
        year,
        month,
        day,
        hour,
        minute,
        second,
        microsecond,
        datetime.timezone.utc,
    )


def timestamp_date(timestamp):
    """Keep only the date part of a datetime-represented timestamp."""
    return datetime.datetime(
        year=timestamp.year,
        month=timestamp.month,
        day=timestamp.day,
        tzinfo=datetime.timezone.utc,
    )


def utcfromtimestamp(timestamp):
    """Create a ``datetime`` object from timestamp.

    Unlike stdlib's ``utcfromtimestamp``, this also sets ``tzinfo`` to
    UTC; without this, ``timestamp()`` will return incorrect number.
    """
    return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)


def utcnow():
    """Return a ``datetime`` object of now.

    Unlike stdlib's ``utcnow``, this also sets ``tzinfo`` to UTC;
    without this, ``timestamp()`` will return incorrect number.
    """
    return datetime.datetime.now(datetime.timezone.utc)


UNIX_EPOCH = utcfromtimestamp(0)
