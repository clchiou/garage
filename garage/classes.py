"""Helpers for writing classes."""

__all__ = [
    'LazyAttrs',
]


class LazyAttrs:
    """Compute (and store) attributes lazily."""

    def __init__(self, compute_attrs):
        self.__compute_attrs = compute_attrs
        self.__attrs = {}

    def __getattr__(self, name):
        if name not in self.__attrs:
            self.__compute_attrs(name, self.__attrs)
        return self.__attrs[name]
