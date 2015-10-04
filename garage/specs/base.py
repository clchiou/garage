__all__ = [
    'make_as_dict',
    'make_as_namespace',
]

from collections import OrderedDict
from functools import partial
from itertools import chain

from garage import preconds
from garage.collections import DictAsAttrs
from garage.models import AutoDerefDictProxy


def make_as_dict(fields, cls=dict):
    return partial(as_dict, cls=cls, names=tuple(f.name for f in fields))


def as_dict(obj, cls, names):
    return cls((name, getattr(obj, name)) for name in names)


def make_as_namespace(fields):
    return partial(as_namespace, [f.name for f in fields])


def as_namespace(names, *args, **kwargs):
    data = OrderedDict(chain(
        zip(names, args),
        ((name, kwargs[name]) for name in names if name in kwargs),
    ))
    preconds.check_argument(len(names) == len(data))
    return DictAsAttrs(AutoDerefDictProxy(data))
