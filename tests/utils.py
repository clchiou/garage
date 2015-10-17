__all__ = [
    'Any',
]


class Any:

    def __init__(self, klass=object):
        self.klass = klass

    def __eq__(self, instance):
        return issubclass(type(instance), self.klass)
