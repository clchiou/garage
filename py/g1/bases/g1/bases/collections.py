"""Extension of standard library's collections."""

__all__ = [
    'Namespace',
]


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
