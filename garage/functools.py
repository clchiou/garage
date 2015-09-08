__all__ = [
    'run_once',
    'is_ordered',
    'unique',
    'group',
    'memorize',
    'nondata_property',
]

import collections
import functools
import operator

from garage import preconds


def run_once(func):
    """The decorated function will be run only once."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not wrapper.has_run:
            wrapper.has_run = True
            return func(*args, **kwargs)
    wrapper.has_run = False
    return wrapper


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


def group(iterable, key=None):
    """Group elements by key, preserving orders."""
    if key is None:
        key = lambda element: element
    odict = collections.OrderedDict()
    for element in iterable:
        odict.setdefault(key(element), []).append(element)
    return list(odict.values())


def memorize(method):
    """Wrap a method in NondataProperty and then override (i.e.,
       memorize) it with the result.

       Note: method's name _must_ be the same as the property name.
    """
    preconds.check_argument(not isinstance(method, property))
    preconds.check_argument(method.__name__ != '<lambda>')

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
