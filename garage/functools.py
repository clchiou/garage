__all__ = [
    'is_ordered',
    'memorize',
    'nondata_property',
    'unique',
]

import collections
import functools
import operator

import garage.preconds


def is_ordered(lst, key=None, strict=False):
    """True if input list is (strictly) ordered."""
    if key is None:
        key = lambda item: item
    cmp = operator.lt if strict else operator.le
    return all(cmp(key(x0), key(x1)) for x0, x1 in zip(lst, lst[1:]))


def unique(iterable, key=None):
    """Return unique elements of an iterable."""
    if key:
        odict = collections.OrderedDict()
        for element in iterable:
            odict.setdefault(key(element), element)
        return list(odict.values())
    else:
        return list(collections.OrderedDict.fromkeys(iterable))


def memorize(method):
    """Wrap a method and memorize its return value.

       Note: method's name _must_ be the same as the property name.
    """
    garage.preconds.check_arg(not isinstance(method, property))
    garage.preconds.check_arg(method.__name__ != '<lambda>')

    @functools.wraps(method)
    def wrapper(self):
        value = method(self)
        # Override the wrapper before return.
        self.__dict__[method.__name__] = value
        return value

    return nondata_property(wrapper)


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
