"""Helpers for class definitions."""

__all__ = [
    'LazyAttrs',
    'NondataProperty',
    'memorize',
    'nondata_property',
]

import functools

from garage import asserts


class LazyAttrs:
    """Compute (and store) attributes lazily."""

    def __init__(self, compute_attrs):
        self.__compute_attrs = compute_attrs

    def __getattr__(self, name):
        self.__compute_attrs(name, self.__dict__)
        return self.__dict__[name]


class NondataProperty:
    """A non-data descriptor version of property.

       This is "non-data" means that instances may override it.
    """

    def __init__(self, fget=None, doc=None):
        self.fget = fget
        if doc is None and fget is not None:
            doc = fget.__doc__
        self.__doc__ = doc

    def __get__(self, instance, _=None):
        if instance is None:
            return self
        if self.fget is None:
            raise AttributeError('unreadable attribute')
        return self.fget(instance)

    def getter(self, fget):
        return type(self)(fget, self.__doc__)


def nondata_property(fget=None, doc=None):
    return NondataProperty(fget, doc)


def memorize(method):
    """Wrap a method in NondataProperty and then override (i.e.,
       memorize) it with the result.

       Note: method's name _must_ be the same as the property name.
    """
    asserts.not_type_of(method, property)
    asserts.not_equal(method.__name__, '<lambda>')
    @functools.wraps(method)
    def wrapper(self):
        value = method(self)
        # Override the wrapper before return.
        self.__dict__[method.__name__] = value
        return value
    return nondata_property(wrapper)
