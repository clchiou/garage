"""Extension of standard library's collections."""

__all__ = [
    'LoadingDict',
    'LruCache',
    'Multiset',
    'Namespace',
]

import collections
import collections.abc
import operator

from . import classes
from .assertions import ASSERT


# Since we are not overriding any methods, ``LoadingDict`` should
# probably inherit from ``dict``, not ``collections.UserDict``.
class LoadingDict(dict):

    def __init__(self, load, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__load = load

    def __missing__(self, key):
        value = self.__load(key)
        self[key] = value
        return value


class LruCache(collections.abc.MutableMapping):
    """LRU cache.

    In general, entry-wise methods, such as ``__contains__``, always
    alter cache eviction order, and methods that operate on the entire
    cache, such as ``len`` and ``items``, do not.
    """

    __slots__ = ('capacity', '_cache')

    def __init__(self, capacity):
        self.capacity = ASSERT.greater(capacity, 0)
        self._cache = collections.OrderedDict()

    #
    # Do not use ``MutableMapping``'s implementation of ``keys``,
    # ``items``, and ``values``.  Implement them ourselves to ensure
    # that they do not alter cache eviction order (well, ``keys`` is
    # actually fine to use ``MutableMapping``'s, but anyway).
    #

    def keys(self):
        return collections.abc.KeysView(self._cache)

    def items(self):
        return collections.abc.ItemsView(self._cache)

    def values(self):
        return collections.abc.ValuesView(self._cache)

    def __len__(self):
        return len(self._cache)

    def __iter__(self):
        yield from self._cache

    def __getitem__(self, key):
        value = self._cache[key]
        self._cache.move_to_end(key)
        return value

    def __setitem__(self, key, value):
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > self.capacity:
            self._cache.popitem(last=False)

    def __delitem__(self, key):
        del self._cache[key]


class Multiset:

    def __init__(self, iterable=(), *, _elements=None, _num_elements=None):
        if _elements is None:
            self._elements = collections.Counter()
            self._num_elements = 0
            for element in iterable:
                self.add(element)
        else:
            self._elements = _elements
            self._num_elements = _num_elements or sum(self._elements.values())

    def copy(self):
        return Multiset(
            _elements=self._elements.copy(),
            _num_elements=self._num_elements,
        )

    __repr__ = classes.make_repr(
        '{{{items}}}',
        items=lambda self: ', '.
        join('%r: %d' % pair for pair in self._elements.items()),
    )

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

    def isdisjoint(self, other):
        ASSERT.isinstance(other, Multiset)
        return all(value not in other for value in self._elements)

    def _compare_counts(self, other, op):
        ASSERT.isinstance(other, Multiset)
        return all(
            op(count, other.count(value))
            for value, count in self._elements.items()
        )

    def __le__(self, other):
        return self._compare_counts(other, operator.le)

    issubset = __le__

    def __lt__(self, other):
        return (
            self._compare_counts(other, operator.le)
            and len(self) < len(other)
        )

    def __gt__(self, other):
        return ASSERT.isinstance(other, Multiset).__lt__(self)

    def __ge__(self, other):
        return ASSERT.isinstance(other, Multiset).__le__(self)

    issuperset = __ge__

    def __eq__(self, other):
        return (
            self._compare_counts(other, operator.eq)
            and len(self) == len(other)
        )

    def _apply(self, other, op):
        ASSERT.isinstance(other, Multiset)
        return Multiset(_elements=op(self._elements, other._elements))

    def _iapply(self, other, iop):
        ASSERT.isinstance(other, Multiset)
        iop(self._elements, other._elements)
        self._num_elements = sum(self._elements.values())
        return self

    def __and__(self, other):
        return self._apply(other, operator.and_)

    intersection = __rand__ = __and__

    def __iand__(self, other):
        return self._iapply(other, operator.iand)

    intersection_update = __iand__

    def __or__(self, other):
        return self._apply(other, operator.or_)

    union = __ror__ = __or__

    def __ior__(self, other):
        return self._iapply(other, operator.ior)

    union_update = __ior__

    def _xor_counts(self, other):
        ASSERT.isinstance(other, Multiset)
        return ((self._elements - other._elements) +
                (other._elements - self._elements))

    def __xor__(self, other):
        return Multiset(_elements=self._xor_counts(other))

    symmetric_difference = __rxor__ = __xor__

    def __ixor__(self, other):
        self._elements = self._xor_counts(other)
        self._num_elements = sum(self._elements.values())
        return self

    symmetric_difference_update = __ixor__

    def __add__(self, other):
        return self._apply(other, operator.add)

    __radd__ = __add__

    def __iadd__(self, other):
        return self._iapply(other, operator.iadd)

    update = __iadd__

    def __sub__(self, other):
        return self._apply(other, operator.sub)

    difference = __sub__

    def __rsub__(self, other):
        return other.__sub__(self)

    def __isub__(self, other):
        return self._iapply(other, operator.isub)

    difference_update = __isub__

    def count(self, value):
        return self._elements[value]

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

    def remove(self, value):
        if value not in self:
            raise KeyError(value)
        self.discard(value)

    def pop(self):
        try:
            value = next(iter(self))
        except StopIteration:
            raise KeyError from None
        self.discard(value)
        return value

    def clear(self):
        self._elements.clear()
        self._num_elements = 0


collections.abc.MutableSet.register(Multiset)


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

    __repr__ = classes.make_repr(
        '{{{entries}}}',
        entries=lambda self: ', '.
        join('%s=%r' % pair for pair in self._entries.items()),
    )

    def __iter__(self):
        return iter(self._entries)

    def _asdict(self):
        return self._entries.copy()

    def __contains__(self, name):
        return name in self._entries

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
