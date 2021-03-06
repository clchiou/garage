"""Helpers for working with classes."""

__all__ = [
    'SingletonMeta',
    'abstract_method',
    'abstract_property',
    'get_public_method_names',
    'make_repr',
    'memorizing_property',
    'nondata_property',
]

import functools
import inspect

from .assertions import ASSERT


class SingletonMeta(type):
    """Metaclass to create singleton types."""

    def __call__(cls, *args, **kwargs):
        # Should I add a lock to make this thread-safe?
        try:
            instance = cls.__instance
        except AttributeError:
            instance = cls.__instance = super().__call__(*args, **kwargs)
        return instance


class nondata_property:
    """Non-data descriptor variant of property.

    See: https://docs.python.org/3/howto/descriptor.html#descriptor-protocol
    """

    def __init__(self, fget=None, doc=None):
        self.fget = fget
        if doc is None and fget is not None:
            doc = fget.__doc__
        self.__doc__ = doc

    def __get__(self, obj, type=None):  # pylint: disable=redefined-builtin
        if obj is None:
            return self
        if self.fget is None:
            raise AttributeError('unreadable attribute')
        return self.fget(obj)


def abstract_method(self, *args, **kwargs):  # pylint: disable=unused-argument
    raise NotImplementedError


abstract_property = nondata_property(abstract_method)


def memorizing_property(func):
    """Non-data property decorator that memorizes its value.

    It stores the value to the instance by function's name; so ``func``
    cannot be a nameless entity such as a lambda function.
    """
    ASSERT.not_equal(func.__name__, '<lambda>')

    @nondata_property
    @functools.wraps(func)
    def wrapper(self):
        value = func(self)
        setattr(self, func.__name__, value)
        return value

    return wrapper


def get_public_method_names(obj_or_cls):
    """Return public method names of the given class.

    This excludes names of other callable objects like (inner) classes,
    class methods, and static methods.
    """
    cls = obj_or_cls if inspect.isclass(obj_or_cls) else obj_or_cls.__class__
    return tuple(
        name for name, _ in inspect.getmembers(cls, inspect.isfunction) if (
            not name.startswith('_') and
            not isinstance(inspect.getattr_static(cls, name), staticmethod)
        )
    )


def make_repr(template='', **extractors):
    """Make ``__repr__``."""

    ASSERT.not_in('self', extractors)
    ASSERT.not_in('__self_id', extractors)
    if not template:
        ASSERT.empty(extractors)

    template = (
        '<'
        '{self.__class__.__module__}.'
        '{self.__class__.__qualname__} '
        '{__self_id:#x}'
        '%s%s'
        '>'
    ) % (template and ' ', template or '')

    extractors = tuple(extractors.items())

    if extractors:

        def __repr__(self):
            kwargs = {name: extractor(self) for name, extractor in extractors}
            return template.format(self=self, __self_id=id(self), **kwargs)

    else:

        def __repr__(self):
            return template.format(self=self, __self_id=id(self))

    return __repr__
