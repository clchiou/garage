__all__ = [
    'to_milliseconds_int',
]

from g1.bases import times


def to_milliseconds_int(seconds):
    return int(
        times.convert(times.Units.SECONDS, times.Units.MILLISECONDS, seconds)
    )
