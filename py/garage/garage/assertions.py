__all__ = [
    'ASSERT',
    'Assertions',
]


class Assertions:

    def __init__(self, exc_type):
        self._exc_type = exc_type

    def __call__(self, cond, message, *args):
        if not cond:
            raise self._exc_type(message % args)
        return cond

    def fail(self, message, *args):
        raise self._exc_type(message % args)

    def true(self, value):
        self(value, 'expect truth instead of %r', value)
        return value

    def false(self, value):
        self(not value, 'expect falsehood instead of %r', value)
        return value

    def is_(self, value, expected):
        self(value is expected, 'expect %r is %r', value, expected)
        return value

    def is_not(self, value, expected):
        self(value is not expected, 'expect %r is not %r', value, expected)
        return value

    def none(self, value):
        self(value is None, 'expect None instead of %r', value)
        return value

    def not_none(self, value):
        self(value is not None, 'expect non-None value')
        return value

    def type_of(self, value, type_):
        self(
            isinstance(value, type_),
            'expect %r-typed value instead of %r', type_, value,
        )
        return value

    def not_type_of(self, value, type_):
        self(
            not isinstance(value, type_),
            'expect not %r-typed value instead of %r', type_, value,
        )
        return value

    def in_(self, member, container):
        self(member in container, 'expect %r in %r', member, container)
        return member

    def not_in(self, member, container):
        self(member not in container, 'expect %r not in %r', member, container)
        return member

    def equal(self, value, expected):
        self(value == expected, 'expect %r == %r', value, expected)
        return value

    def not_equal(self, value, expected):
        self(value != expected, 'expect %r != %r', value, expected)
        return value

    def greater(self, value, expected):
        self(value > expected, 'expect %r > %r', value, expected)
        return value

    def greater_or_equal(self, value, expected):
        self(value >= expected, 'expect %r >= %r', value, expected)
        return value

    def less(self, value, expected):
        self(value < expected, 'expect %r < %r', value, expected)
        return value

    def less_or_equal(self, value, expected):
        self(value <= expected, 'expect %r <= %r', value, expected)
        return value


ASSERT = Assertions(AssertionError)
