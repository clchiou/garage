"""Helpers for working with classes."""

__all__ = [
    'SingletonMeta',
]


class SingletonMeta(type):
    """Metaclass to create singleton types."""

    def __call__(cls, *args, **kwargs):
        # Should I add a lock to make this thread-safe?
        try:
            instance = cls.__instance
        except AttributeError:
            instance = cls.__instance = super().__call__(*args, **kwargs)
        return instance
