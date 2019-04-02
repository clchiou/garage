__all__ = [
    'utcfromtimestamp',
    'utcnow',
]

import datetime


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
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
