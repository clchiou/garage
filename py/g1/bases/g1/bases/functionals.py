"""Functional programming utilities.

I am uncertain about how much functional programming I should adopt in
the codebase.  While Python can do all sorts of functional programming,
it is not ergonomically great for it.  For now, let's just try it bit by
bit, and see how things go.
"""

__all__ = [
    'compose',
    'identity',
]


def identity(x):
    return x


def compose(*funcs):
    """Return a function as the composition of functions.

    >>> compose(str, lambda i: i + 1)(0)
    '1'
    """
    if not funcs:
        return identity
    elif len(funcs) == 1:
        return funcs[0]
    else:
        return Composer(funcs)


class Composer:

    def __init__(self, funcs):
        funcs = tuple(reversed(funcs))
        self._first = funcs[0]
        self._rest = funcs[1:]

    def __repr__(self):
        return '<%s at %#x of: %s>' % (
            self.__class__.__qualname__,
            id(self),
            ', '.join(
                getattr(func, '__name__', None) or repr(func)
                for func in reversed((self._first, ) + self._rest)
            ),
        )

    def __call__(self, *args, **kwargs):
        x = self._first(*args, **kwargs)
        for func in self._rest:
            x = func(x)
        return x
