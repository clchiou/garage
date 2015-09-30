__all__ = [
    'make_dict_builder',
    'make_namedtuple',
]

from collections import OrderedDict, namedtuple
from functools import partialmethod


def make_dict_builder(model, name=None, bases=()):

    def __init__(self, data=None):
        self._data = data.copy() if data else {}

    def __call__(self):
        return OrderedDict(
            (field.name, self._data[field.name]) for field in self._model)

    def setter(self, name, value):
        self._data[name] = value
        return self

    namespace = {
        field.name: partialmethod(setter, field.name) for field in model
    }
    namespace['_model'] = model
    namespace['__init__'] = __init__
    namespace['__call__'] = __call__

    return type(name or model.name, bases, namespace)


def make_namedtuple(model, name=None):
    return namedtuple(name or model.name, [field.name for field in model])
