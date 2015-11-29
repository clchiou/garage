__all__ = [
    'Any',
    'make_sorted_ordered_dict',
]

from collections import OrderedDict


class Any:

    def __init__(self, klass=object):
        self.klass = klass

    def __eq__(self, instance):
        return issubclass(type(instance), self.klass)


def make_sorted_ordered_dict(**kwargs):
    return OrderedDict((key, kwargs[key]) for key in sorted(kwargs))
