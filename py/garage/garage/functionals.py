"""Helpers for functional-style programming."""

__all__ = [
    'run_once',
    'with_defaults',
]

import functools


def run_once(func):
    """The decorated function will be run only once."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not wrapper.has_run:
            wrapper.has_run = True
            return func(*args, **kwargs)
    wrapper.has_run = False
    return wrapper


def with_defaults(func, defaults):
    """Wrap a function with default kwargs."""
    @functools.wraps(func)
    def call_with_defaults(*args, **kwargs):
        kwargs_plus_defaults = defaults.copy()
        kwargs_plus_defaults.update(kwargs)
        return func(*args, **kwargs_plus_defaults)
    return call_with_defaults
