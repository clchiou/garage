__all__ = [
    'OKAY',
    'NOT_OKAY',
]


from enum import Enum


class Okay(Enum):
    OKAY = True
    NOT_OKAY = False

    def __bool__(self):
        return self is Okay.OKAY

    def __invert__(self):
        if self is Okay.OKAY:
            return Okay.NOT_OKAY
        else:
            return Okay.OKAY

    def __and__(self, other):
        if self and other:
            return Okay.OKAY
        else:
            return Okay.NOT_OKAY

    def __or__(self, other):
        if self or other:
            return Okay.OKAY
        else:
            return Okay.NOT_OKAY

    def __xor__(self, other):
        if (self and not other) or (not self and other):
            return Okay.OKAY
        else:
            return Okay.NOT_OKAY


OKAY = Okay.OKAY
NOT_OKAY = Okay.NOT_OKAY
