__all__ = [
    'Units',
    'convert',
]

import enum


class Units(enum.Enum):
    SECONDS = 0
    MILLISECONDS = -3
    MICROSECONDS = -6
    NANOSECONDS = -9


def convert(source_unit, target_unit, time):
    """Convert time between units."""
    if source_unit is target_unit:
        return time
    return time * 10**(source_unit.value - target_unit.value)
