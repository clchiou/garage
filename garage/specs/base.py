__all__ = [
    'make_as_dict',
    'make_namedtuple',
]

from collections import OrderedDict, namedtuple
from functools import partial


def make_as_dict(fields, cls=OrderedDict):
    return partial(as_dict, cls=cls, names=tuple(f.name for f in fields))


def as_dict(obj, cls, names):
    return cls((name, getattr(obj, name)) for name in names)


def make_namedtuple(model, name=None):
    return namedtuple(name or model.name, [field.name for field in model])
