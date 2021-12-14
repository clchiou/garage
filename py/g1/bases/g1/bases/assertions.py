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

import builtins
import operator
from collections import abc
from functools import partialmethod

from . import functionals


def _empty(collection):
    return isinstance(collection, abc.Collection) and not collection


def _not_empty(collection):
    return isinstance(collection, abc.Collection) and collection


def _is_none(x):
    return x is None


def _is_not_none(x):
    return x is not None


def _xor(p, q):
    return bool(p) != bool(q)


def _in(x, xs):
    return x in xs


def _not_in(x, xs):
    return x not in xs


def _in_range(v, pair):
    return pair[0] <= v < pair[1]


def _only_one(xs):
    count = 0
    for x in xs:
        if x:
            count += 1
        if count > 1:
            break
    return count == 1


def _unique(xs):
    seen = set()
    for x in xs:
        if x in seen:
            return False
        seen.add(x)
    return True


def _issubset_proper(u, v):
    return u.issubset(v) and u != v


def _issuperset_proper(u, v):
    return u.issuperset(v) and u != v


# ``_method_caller(name)(obj, *args)`` is equivalent to
# ``operator.methodcaller(name, *args)(obj)``.
def _method_caller(name):
    return lambda obj, *args: getattr(obj, name)(*args)


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

    def unreachable(self, message, *args):
        raise self._make_exc(message.format(*args))

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

    empty = partialmethod(
        _assert_1, _empty, message='expect empty collection, not {!r}'
    )
    not_empty = partialmethod(
        _assert_1, _not_empty, message='expect non-empty collection, not {!r}'
    )

    none = partialmethod(_assert_1, _is_none, message='expect None, not {!r}')
    not_none = partialmethod(
        _assert_1, _is_not_none, message='expect non-None value'
    )

    def predicate(self, arg, predicate, *, message='expect {1}, not {0!r}'):
        if not predicate(arg):
            raise self._make_exc(message.format(arg, predicate), arg)
        return arg

    def not_predicate(
        self, arg, predicate, *, message='expect not {1}, but {0!r}'
    ):
        if predicate(arg):
            raise self._make_exc(message.format(arg, predicate), arg)
        return arg

    def _assert_2(self, predicate, actual, expect, *, message):
        if not predicate(actual, expect):
            msg = message.format(actual, expect)
            raise self._make_exc(msg, actual, expect)
        return actual

    xor = partialmethod(
        _assert_2, _xor, message='expect {0!r} xor {1!r} be true'
    )
    not_xor = partialmethod(
        _assert_2,
        functionals.compose(operator.not_, _xor),
        message='expect {0!r} xor {1!r} be false',
    )

    is_ = partialmethod(
        _assert_2, operator.is_, message='expect {1!r}, not {0!r}'
    )
    is_not = partialmethod(
        _assert_2, operator.is_not, message='expect non-{!r} value'
    )

    isinstance = partialmethod(
        _assert_2,
        builtins.isinstance,
        message='expect {1}-typed value, not {0!r}',
    )
    not_isinstance = partialmethod(
        _assert_2,
        functionals.compose(operator.not_, builtins.isinstance),
        message='expect non-{1}-typed value, but {0!r}',
    )

    issubclass = partialmethod(
        _assert_2,
        builtins.issubclass,
        message='expect subclass of {1}, not {0!r}',
    )
    not_issubclass = partialmethod(
        _assert_2,
        functionals.compose(operator.not_, builtins.issubclass),
        message='expect non-subclass of {1}, but {0!r}',
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

    def zip(self, *sequences):
        """Check all sequences have the same length before zip them."""
        if len(frozenset(map(len, sequences))) > 1:
            raise self._make_exc(
                'expect same length: {}'.format(
                    ', '.join('%d' % len(s) for s in sequences)
                ),
                *sequences,
            )
        return zip(*sequences)

    def getitem(self, collection, key):
        """Shorthand for ``ASSERT.contains(collection, key)[key]``."""
        return self.contains(collection, key)[key]

    def setitem(self, collection, key, value):
        """Check before set an item."""
        self.not_contains(collection, key)[key] = value

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
    in_range = partialmethod(
        _assert_2,
        _in_range,
        message='expect {1[0]!r} <= x < {1[1]!r}, not {0!r}',
    )
    not_in_range = partialmethod(
        _assert_2,
        functionals.compose(operator.not_, _in_range),
        message='expect not {1[0]!r} <= x < {1[1]!r}, not {0!r}',
    )

    startswith = partialmethod(
        _assert_2,
        _method_caller('startswith'),
        message='expect x.startswith({1!r}), not {0!r}',
    )
    not_startswith = partialmethod(
        _assert_2,
        functionals.compose(
            operator.not_,
            _method_caller('startswith'),
        ),
        message='expect not x.startswith({1!r}), not {0!r}',
    )

    isdisjoint = partialmethod(
        _assert_2,
        _method_caller('isdisjoint'),
        message='expect x.isdisjoint({1!r}), not {0!r}',
    )
    not_isdisjoint = partialmethod(
        _assert_2,
        functionals.compose(
            operator.not_,
            _method_caller('isdisjoint'),
        ),
        message='expect not x.isdisjoint({1!r}), but {0!r}',
    )

    issubset = partialmethod(
        _assert_2,
        _method_caller('issubset'),
        message='expect x.issubset({1!r}), not {0!r}',
    )
    not_issubset = partialmethod(
        _assert_2,
        functionals.compose(
            operator.not_,
            _method_caller('issubset'),
        ),
        message='expect not x.issubset({1!r}), but {0!r}',
    )

    issubset_proper = partialmethod(
        _assert_2,
        _issubset_proper,
        message='expect x is proper subset of {1!r}, not {0!r}',
    )
    not_issubset_proper = partialmethod(
        _assert_2,
        functionals.compose(
            operator.not_,
            _issubset_proper,
        ),
        message='expect x is not proper subset of {1!r}, but {0!r}',
    )

    issuperset = partialmethod(
        _assert_2,
        _method_caller('issuperset'),
        message='expect x.issuperset({1!r}), not {0!r}',
    )
    not_issuperset = partialmethod(
        _assert_2,
        functionals.compose(
            operator.not_,
            _method_caller('issuperset'),
        ),
        message='expect not x.issuperset({1!r}), but {0!r}',
    )

    issuperset_proper = partialmethod(
        _assert_2,
        _issuperset_proper,
        message='expect x is proper superset of {1!r}, not {0!r}',
    )
    not_issuperset_proper = partialmethod(
        _assert_2,
        functionals.compose(
            operator.not_,
            _issuperset_proper,
        ),
        message='expect x is not proper superset of {1!r}, but {0!r}',
    )

    def _assert_collection(
        self, predicate, collection, mapper=None, *, message
    ):
        xs = collection
        if mapper is not None:
            xs = map(mapper, xs)
        if not predicate(xs):
            msg = message.format(collection, mapper or 'true')
            raise self._make_exc(msg, collection)
        return collection

    # Given a collection of n elements, let x be the number of elements
    # that satisfies the condition, and the following assertions can be
    # expressed as...

    # Assert x = n.
    all = partialmethod(
        _assert_collection, builtins.all, message='expect all {1}, not {0!r}'
    )
    # Assert 0 <= x < n.
    not_all = partialmethod(
        _assert_collection,
        functionals.compose(operator.not_, builtins.all),
        message='expect not all {1}, not {0!r}',
    )

    # Assert 0 < x <= n.
    any = partialmethod(
        _assert_collection, builtins.any, message='expect any {1}, not {0!r}'
    )
    # Assert x = 0.
    not_any = partialmethod(
        _assert_collection,
        functionals.compose(operator.not_, builtins.any),
        message='expect not any {1}, not {0!r}',
    )

    # Assert x = 1.
    only_one = partialmethod(
        _assert_collection,
        _only_one,
        message='expect only one {1}, not {0!r}',
    )

    unique = partialmethod(
        _assert_collection,
        _unique,
        message='expect unique elements in {0!r}',
    )

    not_unique = partialmethod(
        _assert_collection,
        functionals.compose(operator.not_, _unique),
        message='expect non-unique elements in {0!r}',
    )


ASSERT = Assertions(lambda message, *_: AssertionError(message))
