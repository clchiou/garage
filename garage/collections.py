__all__ = [
    'DictAsAttrs',
    'FixedKeysDict',
    'make_fixed_attrs',
]

from collections import MutableMapping


def make_fixed_attrs(**kwargs):
    """Make a fixed set of attributes."""
    return DictAsAttrs(FixedKeysDict(kwargs))


class DictAsAttrs:
    """Wrap a dict and access its elements through attributes."""

    def __init__(self, data):
        assert '_data' not in data
        object.__setattr__(self, '_data', data)

    def __str__(self):
        return '%s(%r)' % (self.__class__.__name__, self._data)

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self._data)

    def __getattr__(self, name):
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        self._data[name] = value

    def __delattr__(self, name):
        try:
            del self._data[name]
        except KeyError:
            raise AttributeError(name)

    def __dir__(self):
        return self._data.keys()


class FixedKeysDict(MutableMapping):
    """A dict with a fixed set of keys."""

    def __init__(self, *args, **kwargs):
        self._data = dict(*args, **kwargs)

    def __contains__(self, key):
        return key in self._data

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        if key not in self._data:
            raise KeyError(key)
        self._data[key] = value

    def __delitem__(self, key):
        raise NotImplementedError
