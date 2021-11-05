"""List helpers."""

__all__ = [
    'binary_search',
    'lower_bound',
    'upper_bound',
]

import operator

from . import functionals


def binary_search(array, value, *, key=None, reverse=False):
    """Binary search.

    NOTE: It does not guarantee to return the leftmost or rightmost
    index when duplicated target values are present.
    """
    if key is None:
        key = functionals.identity
    less_than = operator.gt if reverse else operator.lt
    left = 0
    right = len(array) - 1
    while left <= right:
        middle = (left + right) // 2
        x = key(array[middle])
        if less_than(x, value):
            left = middle + 1
        elif less_than(value, x):
            right = middle - 1
        else:
            return middle
    raise ValueError('not found: %r' % (value, ))


def lower_bound(array, value, *, key=None, reverse=False):
    if key is None:
        key = functionals.identity
    less_than = operator.gt if reverse else operator.lt
    left = 0
    right = len(array)
    while left < right:
        middle = (left + right) // 2
        if less_than(key(array[middle]), value):
            left = middle + 1
        else:
            right = middle
    return left


def upper_bound(array, value, *, key=None, reverse=False):
    if key is None:
        key = functionals.identity
    less_than = operator.gt if reverse else operator.lt
    left = 0
    right = len(array)
    while left < right:
        middle = (left + right) // 2
        if less_than(value, key(array[middle])):
            right = middle
        else:
            left = middle + 1
    return right
