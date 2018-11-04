"""Extension of standard library's collections."""

__all__ = [
    'Multiset',
    'Namespace',
]

import collections

from g1.bases.assertions import ASSERT


class Multiset(collections.MutableSet):

    def __init__(self, iterable=()):
        self._elements = collections.Counter()
        self._num_elements = 0
        for element in iterable:
            self.add(element)

    def __contains__(self, value):
        return value in self._elements

    def __iter__(self):
        num_elements = self._num_elements
        for element, count in self._elements.items():
            ASSERT(count > 0, 'expect count > 0: {}', self._elements)
            num_elements -= count
            for _ in range(count):
                yield element
        ASSERT(
            num_elements == 0,
            'expect {} elements: {}',
            self._num_elements,
            self._elements,
        )

    def __len__(self):
        return self._num_elements

    def add(self, value):
        self._elements[value] += 1
        self._num_elements += 1

    def discard(self, value):
        count = self._elements.get(value)
        if count is None:
            return
        if count > 1:
            self._elements[value] -= 1
        else:
            self._elements.pop(value)
        self._num_elements -= 1


class Namespace:
    """Read-only namespace."""

    def __init__(self, *nv_pairs, **entries):
        for nv_pair in nv_pairs:
            if isinstance(nv_pair, str):
                name = value = nv_pair
            else:
                name, value = nv_pair
            if name in entries:
                raise ValueError('overwrite entry: %r' % name)
            entries[name] = value
        for name in entries:
            if name.startswith('_'):
                raise ValueError('name %r starts with \'_\'' % name)
        super().__setattr__('_entries', entries)

    def __iter__(self):
        return iter(self._entries)

    def _asdict(self):
        return self._entries.copy()

    def __getitem__(self, name):
        return self._entries[name]

    def __getattr__(self, name):
        try:
            return self._entries[name]
        except KeyError:
            message = (
                '%r object has no attribute %r' %
                (self.__class__.__name__, name)
            )
            raise AttributeError(message) from None

    def __setattr__(self, name, value):
        raise TypeError(
            '%r object does not support attribute assignment' %
            self.__class__.__name__
        )
