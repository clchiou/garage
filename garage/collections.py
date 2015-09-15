__all__ = [
    'Namespace',
    'DictAsAttrs',
    'FixedKeysDict',
    'ImmutableSortedDict',
]

from collections import OrderedDict
from collections import Mapping
from collections import MutableMapping


class DictAsAttrs:
    """Wrap a dict and access its elements through attributes."""

    def __init__(self, data):
        assert '_DictAsAttrs__data' not in data
        object.__setattr__(self, '_DictAsAttrs__data', data)

    def __str__(self):
        return '%s(%r)' % (self.__class__.__name__, self.__data)

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self.__data)

    def __getattr__(self, name):
        try:
            return self.__data[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        try:
            self.__data[name] = value
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __delattr__(self, name):
        try:
            del self.__data[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __dir__(self):
        yield from sorted(self.__data.keys())


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
        raise KeyError(key)


class Namespace(DictAsAttrs):

    def __init__(self, **kwargs):
        super().__init__(FixedKeysDict(**kwargs))

    def __str__(self):
        fields = ', '.join(
            '%s=%r' % (name, getattr(self, name)) for name in dir(self)
        )
        return '%s(%s)' % (self.__class__.__name__, fields)

    def __repr__(self):
        fields = ', '.join(
            '%s=%r' % (name, getattr(self, name)) for name in dir(self)
        )
        return '%s(%s)' % (self.__class__.__name__, fields)


class ImmutableSortedDict(Mapping):

    def __init__(self, **kwargs):
        self._data = OrderedDict((key, kwargs[key]) for key in sorted(kwargs))

    def __getitem__(self, key):
        return self._data[key]

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter(self._data)
