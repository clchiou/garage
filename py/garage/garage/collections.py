"""Collections of objects and collection helper functions."""

__all__ = [
    'DictBuilder',
    'DictViewAttrs',
    'LoadingDict',
    'Symbols',
    'Trie',
    'collect',
    'collect_pairs',
    'group',
    'is_ordered',
    'unique',
]

import operator
from collections import OrderedDict, UserDict


def is_ordered(lst, key=None, strict=False):
    """True if input list is (strictly) ordered."""
    if key is None:
        key = lambda item: item
    cmp = operator.lt if strict else operator.le
    return all(cmp(key(x0), key(x1)) for x0, x1 in zip(lst, lst[1:]))


def unique(iterable, key=None):
    """Return unique elements of an iterable."""
    if key:
        odict = OrderedDict()
        for element in iterable:
            odict.setdefault(key(element), element)
        return list(odict.values())
    else:
        return list(OrderedDict.fromkeys(iterable))


def collect(iterable, key=None, value=None):
    """Collect elements by key, preserving order."""
    if key is None:
        key = lambda element: element
    if value is None:
        value = lambda element: element
    odict = OrderedDict()
    for element in iterable:
        odict.setdefault(key(element), []).append(value(element))
    return odict


def collect_pairs(iterable):
    """Collect pairs, preserving order."""
    return collect(
        iterable, key=lambda pair: pair[0], value=lambda pair: pair[1])


def group(iterable, key=None):
    """Group elements by key, preserving order."""
    return list(collect(iterable, key=key).values())


class DictBuilder:
    """A fluent-style builder of dict object."""

    # It does not support nested if-block at the moment

    def __init__(self, data=None):
        # Don't make a copy because we want to modify it in place
        self.dict = data if data is not None else {}

        # Use finite state machine to parse non-nested if-elif-else
        self._state = None
        # True if we have chosen one of the if-elif-else branch
        self._branch_chosen = False
        # True if we should execute this instruction
        self._predicate = True

    def if_(self, condition):
        assert self._state is None
        self._state = 'if'
        self._branch_chosen = self._predicate = condition
        return self

    def elif_(self, condition):
        assert self._state == 'if'
        if self._branch_chosen:
            self._predicate = False
        else:
            self._branch_chosen = self._predicate = condition
        return self

    def else_(self):
        assert self._state == 'if'
        self._state = 'else'
        if self._branch_chosen:
            self._predicate = False
        else:
            self._branch_chosen = self._predicate = True
        return self

    def end(self):
        assert self._state in ('if', 'else')
        self._state = None
        self._branch_chosen = False
        self._predicate = True
        return self

    # Setter methods

    def assert_(self, assertion):
        if self._predicate:
            if not assertion(self.dict):
                raise AssertionError
        return self

    def setitem(self, key, value):
        if self._predicate:
            self.dict[key] = value
        return self

    def setdefault(self, key, default):
        if self._predicate:
            self.dict.setdefault(key, default)
        return self

    def call(self, key, func):
        if self._predicate:
            func(self.dict[key])
        return self

    def call_and_update(self, key, func):
        if self._predicate:
            self.dict[key] = func(self.dict[key])
        return self


class LoadingDict(UserDict):

    def __init__(self, load, data=None):
        super().__init__(**(data or {}))
        self.load = load

    def __missing__(self, key):
        value = self.load(key)
        self[key] = value
        return value


class DictViewAttrs:
    """Access dict through a namespace."""

    def __init__(self, data):
        assert '_DictViewAttrs__data' not in data
        object.__setattr__(self, '_DictViewAttrs__data', data)

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

    def __iter__(self):
        return iter(self.__data.keys())


class Symbols:
    """Read-only namespace."""

    def __init__(self, *nv_pairs, **symbols):
        for nv_pair in nv_pairs:
            if isinstance(nv_pair, str):
                name = value = nv_pair
            else:
                name, value = nv_pair
            if name in symbols:
                raise ValueError('overwrite name %r' % name)
            if name.startswith('_'):
                raise ValueError('symbol name %r starts with \'_\'' % name)
            symbols[name] = value
        # Return keys in deterministic order (i.e., sorted).
        symbols = OrderedDict((key, symbols[key]) for key in sorted(symbols))
        super().__setattr__('_Symbols__symbols', symbols)

    def __iter__(self):
        return iter(self.__symbols)

    def _asdict(self):
        return self.__symbols.copy()

    def __getattr__(self, name):
        try:
            return self.__symbols[name]
        except KeyError:
            msg = ('%r object has no attribute %r' %
                   (self.__class__.__name__, name))
            raise AttributeError(msg) from None

    def __setattr__(self, name, value):
        raise TypeError('%r object does not support attribute assignment' %
                        self.__class__.__name__)


class Trie:

    EMPTY = object()

    class Node:

        def __init__(self, parent, value):
            self.parent = parent
            self.children = {}
            self.value = value

        def get(self, key, exact, default):
            node = self._get_node(key, exact)
            if node is None or (exact and node.value is Trie.EMPTY):
                return default
            while node and node.value is Trie.EMPTY:
                node = node.parent
            return node.value if node else default

        def _get_node(self, key, exact):
            node = self
            for element in key:
                child = node.children.get(element)
                if child is None:
                    return None if exact else node
                node = child
            return node

        def get_values(self, key):
            node = self
            for i, element in enumerate(key):
                if node.value is not Trie.EMPTY:
                    yield key[:i], node.value
                child = node.children.get(element)
                if child is None:
                    break
                node = child
            else:
                if node.value is not Trie.EMPTY:
                    yield key, node.value

        def values(self):
            if self.value is not Trie.EMPTY:
                yield self.value
            children = sorted(self.children.items(), key=lambda kv: kv[0])
            for _, child in children:
                yield from child.values()

        def upsert(self, key, value):
            node = self
            for i, element in enumerate(key):
                child = node.children.get(element)
                if child is None:
                    for new_element in key[i:]:
                        new_child = Trie.Node(node, Trie.EMPTY)
                        node.children[new_element] = new_child
                        node = new_child
                    break
                node = child
            node.value = value

    def __init__(self):
        self._root = Trie.Node(None, Trie.EMPTY)

    def get(self, key, default=None, *, exact=True):
        return self._root.get(key, exact, default)

    def get_values(self, key):
        return self._root.get_values(key)

    def __getitem__(self, key):
        value = self.get(key, Trie.EMPTY)
        if value is Trie.EMPTY:
            raise KeyError(key)
        return value

    def values(self):
        return self._root.values()

    def __setitem__(self, key, value):
        self._root.upsert(key, value)
