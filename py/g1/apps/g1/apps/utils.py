"""Utilities for external users."""

__all__ = [
    'define_binder',
    'define_binder_for',
    'define_maker',
    'depend_parameter_for',
    'get_annotations',
]

import functools
import inspect

from startup import startup

from . import parameters


def get_annotations(func):
    signature = inspect.signature(func)
    annotations = {
        p.name: p.annotation
        for p in signature.parameters.values()
        if p.annotation is not p.empty
    }
    if signature.return_annotation is not signature.empty:
        annotations['return'] = signature.return_annotation
    return annotations


def _prepare(defaults, kwargs):
    # Since ``startup`` only calls functions once, it should be fine to
    # update ``defaults`` directly.
    if defaults is None:
        defaults = {}
    defaults.update(kwargs)
    for name in defaults:
        value = defaults[name]
        if isinstance(value, parameters.Parameter):
            defaults[name] = value.get()
    return defaults


def define_binder(func, func_label, annotations=None, defaults=None):
    """Define a binder function and add it to ``startup``.

    This is a helper for this common pattern:

    .. code-block:: python

        def f(x: 'x') -> 'y':
            return x * x

        @startup
        def bind_f(x: 'x') -> 'f':
            if isinstance(x, Parameter):
                x = x.get()
            return functools.partial(f, x=x)

    It is shortened to:
    >>> bind_f = define_binder(f, 'f')
    """

    # Since ``startup`` only calls ``bind`` once, it should be fine to
    # update ``defaults`` directly.
    def bind(**kwargs):
        return functools.partial(func, **_prepare(defaults, kwargs))

    bind.__name__ = bind.__qualname__ = 'bind_%s' % func.__name__

    bind_annotations = get_annotations(func)
    bind_annotations.update(annotations or ())
    bind_annotations['return'] = func_label

    return startup.add_func(bind, bind_annotations)


def define_binder_for(func_label, annotations=None, defaults=None):
    """Return a decorator for ``define_binder``.

    Examples:
    >>> @define_binder_for('f')
    ... def f(x: 'x') -> 'y':
    ...     return x * x
    """

    def decorate(func):
        define_binder(func, func_label, annotations, defaults)
        return func

    return decorate


def define_maker(func, annotations=None, defaults=None):
    """Define a maker function and add it to ``startup``.

    This is slightly more versatile than ``startup.add_func``.
    """

    # Since ``startup`` only calls ``make`` once, it should be fine to
    # update ``defaults`` directly.
    def make(**kwargs):
        return func(**_prepare(defaults, kwargs))

    make.__name__ = make.__qualname__ = 'make_%s' % func.__name__

    make_annotations = get_annotations(func)
    make_annotations.update(annotations or ())

    return startup.add_func(make, make_annotations)


def depend_parameter_for(label, value):
    """Add a dependency on parameter initialization for ``value``.

    You need this when you want to use parameter value during starting
    up, where you need to sequence the access to be after parameter
    initialization.
    """
    startup.add_func(
        lambda _: value,
        {
            '_': parameters.LABELS.parameters,
            'return': label,
        },
    )
    return label
