__all__ = [
    'precond',
    'postcond',
    'true',
    'not_true',
    'none',
    'not_none',
    'type_of',
    'not_type_of',
    'equal',
    'not_equal',
]


def precond(cond, message='precondition fails', *args):
    _assert(cond, message, *args)


def postcond(cond, message='postcondition fails', *args):
    _assert(cond, message, *args)


def true(value):
    _assert(value, 'expect truth instead of %r', value)
    return value


def not_true(value):
    _assert(not value, 'expect falsehood instead of %r', value)
    return value


def none(value):
    _assert(value is None, 'expect None instead of %r', value)
    return value


def not_none(value):
    _assert(value is not None, 'expect non-None value')
    return value


def type_of(value, type_):
    _assert(isinstance(value, type_),
            'expect %r-typed value instead of %r', type_, value)
    return value


def not_type_of(value, type_):
    _assert(not isinstance(value, type_),
            'expect not %r-typed value instead of %r', type_, value)
    return value


def equal(value, expected):
    _assert(value == expected, 'expect %r == %r', expected, value)
    return value


def not_equal(value, expected):
    _assert(value != expected, 'expect %r != %r', expected, value)
    return value


def _assert(cond, message, *args):
    if not cond:
        raise AssertionError(message % args)
