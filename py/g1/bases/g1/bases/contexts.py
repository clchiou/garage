__all__ = [
    'Context',
]

import collections

from . import classes
from .assertions import ASSERT


class Context:
    """Context.

    This is just a thin wrapper of collections.ChainMap.
    """

    def __init__(self, content=None, *, _context=None):
        if _context is not None:
            ASSERT.none(content)
            self._context = _context
            return
        if content is None:
            content = {}
        self._context = collections.ChainMap(content)

    __repr__ = classes.make_repr('{self._context!r}')

    def make(self, content=None, *, allow_overwrite=False):
        if content is None:
            content = {}
        if not allow_overwrite:
            ASSERT.isdisjoint(frozenset(content), self._context)
        return Context(_context=self._context.new_child(content))

    def get(self, key, default=None):
        return self._context.get(key, default)

    def set(self, key, value, *, allow_overwrite=False):
        if not allow_overwrite:
            ASSERT.not_in(key, self._context)
        self._context[key] = value

    def asdict(self):
        """Return content as a dict; useful for testing."""
        return dict(self._context)
