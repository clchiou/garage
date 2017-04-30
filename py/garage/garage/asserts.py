__all__ = [
    'Assertions',
    'precond',
    'postcond',
    'true',
    'false',
    'is_',
    'is_not',
    'none',
    'not_none',
    'type_of',
    'not_type_of',
    'in_',
    'not_in',
    'equal',
    'not_equal',
    'greater',
    'greater_or_equal',
    'less',
    'less_or_equal',
]


class Assertions:

    def __init__(self, exc_type):
        self._exc_type = exc_type

    def _assert(self, cond, message, *args):
        if not cond:
            raise self._exc_type(message % args)

    def precond(self, cond, message, *args):
        self._assert(cond, message, *args)

    def postcond(self, cond, message, *args):
        self._assert(cond, message, *args)

    def true(self, value):
        self._assert(value, 'expect truth instead of %r', value)
        return value

    def false(self, value):
        self._assert(not value, 'expect falsehood instead of %r', value)
        return value

    def is_(self, value, expected):
        self._assert(value is expected, 'expect %r is %r', value, expected)
        return value

    def is_not(self, value, expected):
        self._assert(
            value is not expected, 'expect %r is not %r', value, expected)
        return value

    def none(self, value):
        self._assert(value is None, 'expect None instead of %r', value)
        return value

    def not_none(self, value):
        self._assert(value is not None, 'expect non-None value')
        return value

    def type_of(self, value, type_):
        self._assert(
            isinstance(value, type_),
            'expect %r-typed value instead of %r', type_, value)
        return value

    def not_type_of(self, value, type_):
        self._assert(
            not isinstance(value, type_),
            'expect not %r-typed value instead of %r', type_, value)
        return value

    def in_(self, member, container):
        self._assert(member in container, 'expect %r in %r', member, container)
        return member

    def not_in(self, member, container):
        self._assert(
            member not in container, 'expect %r not in %r', member, container)
        return member

    def equal(self, value, expected):
        self._assert(value == expected, 'expect %r == %r', value, expected)
        return value

    def not_equal(self, value, expected):
        self._assert(value != expected, 'expect %r != %r', value, expected)
        return value

    def greater(self, value, expected):
        self._assert(value > expected, 'expect %r > %r', value, expected)
        return value

    def greater_or_equal(self, value, expected):
        self._assert(value >= expected, 'expect %r >= %r', value, expected)
        return value

    def less(self, value, expected):
        self._assert(value < expected, 'expect %r < %r', value, expected)
        return value

    def less_or_equal(self, value, expected):
        self._assert(value <= expected, 'expect %r <= %r', value, expected)
        return value


ASSERTIONS = Assertions(AssertionError)


globals().update(
    (name, getattr(ASSERTIONS, name))
    for name in vars(Assertions)
    if not name.startswith('_')
)
