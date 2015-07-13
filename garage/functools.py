__all__ = [
    'is_ordered',
    'memorize',
    'nondata_property',
]

import operator


def is_ordered(lst, key=None, strict=False):
    """True if input list is (strictly) ordered."""
    if key is None:
        key = lambda item: item
    cmp = operator.lt if strict else operator.le
    return all(cmp(key(x0), key(x1)) for x0, x1 in zip(lst, lst[1:]))


def memorize(method):
    """Wrap a property/method and memorize its return value."""
    is_property = isinstance(method, property)
    wrapped = method
    if is_property:
        method = method.fget

    def wrapper(self):
        if 'value' not in wrapper.__dict__:
            wrapper.value = method(self)
        return wrapper.value

    wrapper.__doc__ = wrapped.__doc__
    return property(wrapper) if is_property else wrapper


class nondata_property:
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
