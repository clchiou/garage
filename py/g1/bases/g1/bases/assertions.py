"""Assertions.

Generally you just use the ``ASSERT`` object defined in this module, but
if you want to raise different exception, just define an ``Assertions``
instance.

Examples:
>>> from g1.bases.assertions import ASSERT
>>> ASSERT(is_prime(x), 'expect a prime number, not {}', x)

This module is different from (and better than, in my opinion) the
assert statement in the following ways:

* You cannot turn it off (the assert statement can be turned off).
* It provides some common checks and default error messages.
* You may raise other exceptions, not just AssertionError.
"""

__all__ = [
    'ASSERT',
    'Assertions',
]

import operator
from functools import partialmethod

from g1.bases import functionals


def _is_none(x):
    return x is None


def _is_not_none(x):
    return x is not None


def _in(x, xs):
    return x in xs


def _not_in(x, xs):
    return x not in xs


class Assertions:
    """Assertions.

    This class provides common assertion methods for asserting program
    states.

    By convention, all assertion methods return the first argument on
    success.  When raising an exception, the default error message is
    composed under the convention that the second argument is what you
    expect and the first argument is the actual input.

    You may provide error message through the keyword-only ``message``
    argument.  Note that messages are ``{}``-formatted, not ``%``-
    formatted.  The benefits of ``{}``-formatting are that you may
    reverse or repeat the formatting arguments in the output message.

    Examples:
    >>> HTTP_ASSERT = Assertions(HttpError)
    >>> x = HTTP_ASSERT.greater(x, 0)
    """

    def __init__(self, make_exc):
        self._make_exc = make_exc

    def __call__(self, cond, message, *args):
        """State an assertion.

        Note that ``__call__`` function signature is slightly different
        here: The formatting arguments are passed from ``*args``, and do
        not include the condition stated by the assertion.

        Examples:
        >>> ASSERT(is_prime(x), 'expect a prime number, not {}', x)
        """
        if not cond:
            raise self._make_exc(message.format(*args), cond)
        return cond

    def _assert_1(self, predicate, arg, *, message):
        if not predicate(arg):
            raise self._make_exc(message.format(arg), arg)
        return arg

    true = partialmethod(
        _assert_1, bool, message='expect true-value, not {!r}'
    )
    false = partialmethod(
        _assert_1, operator.not_, message='expect false-value, not {!r}'
    )

    none = partialmethod(_assert_1, _is_none, message='expect None, not {!r}')
    not_none = partialmethod(
        _assert_1, _is_not_none, message='expect non-None value'
    )

    def _assert_2(self, predicate, actual, expect, *, message):
        if not predicate(actual, expect):
            msg = message.format(actual, expect)
            raise self._make_exc(msg, actual, expect)
        return actual

    is_ = partialmethod(
        _assert_2, operator.is_, message='expect {1!r}, not {0!r}'
    )
    is_not = partialmethod(
        _assert_2, operator.is_not, message='expect non-{!r} value'
    )

    type_of = partialmethod(
        _assert_2, isinstance, message='expect {1}-typed value, not {0!r}'
    )
    not_type_of = partialmethod(
        _assert_2,
        functionals.compose(operator.not_, isinstance),
        message='expect non-{1}-typed value, but {0!r}',
    )

    in_ = partialmethod(_assert_2, _in, message='expect {0!r} in {1!r}')
    not_in = partialmethod(
        _assert_2, _not_in, message='expect {0!r} not in {1!r}'
    )

    contains = partialmethod(
        _assert_2, operator.contains, message='expect {0!r} containing {1!r}'
    )
    not_contains = partialmethod(
        _assert_2,
        functionals.compose(operator.not_, operator.contains),
        message='expect {0!r} not containing {1!r}',
    )

    equal = partialmethod(
        _assert_2, operator.eq, message='expect x == {1!r}, not {0!r}'
    )
    not_equal = partialmethod(
        _assert_2, operator.ne, message='expect x != {1!r}, not {0!r}'
    )
    greater = partialmethod(
        _assert_2, operator.gt, message='expect x > {1!r}, not {0!r}'
    )
    greater_or_equal = partialmethod(
        _assert_2, operator.ge, message='expect x >= {1!r}, not {0!r}'
    )
    less = partialmethod(
        _assert_2, operator.lt, message='expect x < {1!r}, not {0!r}'
    )
    less_or_equal = partialmethod(
        _assert_2, operator.le, message='expect x <= {1!r}, not {0!r}'
    )


ASSERT = Assertions(AssertionError)
