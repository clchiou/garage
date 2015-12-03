__all__ = [
    'C',
    'ObjectBase',
]

import logging

from garage.collections import DictViewAttrs

from . import loader
from .utils import not_null


LOG = logging.getLogger(__name__)


C = DictViewAttrs(loader.load())


class Spec:

    def __init__(self, *, name, ctor, dtor, enter=None, exit=None, fields=(),
                 level=logging.DEBUG):
        self.name = name
        self.ctor = ctor
        self.dtor = dtor
        self.enter = enter
        self.exit = exit
        self.fields = fields
        self.level = level

    def make_init(self):
        name, ctor, level = self.name, self.ctor, self.level
        fields = self.fields
        def __init__(self, *args, **kwargs):
            LOG.log(level, 'new %s', name)
            self.__dict__[name] = not_null(ctor(*map(not_null, args)))
            self.__dict__.update((fname, kwargs[fname]) for fname in fields)
        return __init__

    def make_close(self):
        name, dtor, level = self.name, self.dtor, self.level
        def close(self):
            LOG.log(level, 'delete %s', name)
            dtor(not_null(self.__dict__.pop(name)))
        return close

    def make_enter(self):
        name, enter, level = self.name, self.enter, self.level
        def __enter__(self):
            LOG.log(level, 'enter %s', name)
            enter(not_null(self.__dict__[name]))
            return self
        return __enter__

    def make_exit(self):
        name, exit_, level = self.name, self.exit, self.level
        def __exit__(self, *_):
            LOG.log(level, 'exit %s', name)
            exit_(not_null(self.__dict__[name]))
        return __exit__


class ObjectBaseMeta(type):

    def __new__(mcs, name, bases, namespace):
        for spec in namespace.values():
            if isinstance(spec, Spec):
                LOG.debug('add wrapper methods to %s', name)
                namespace['__init__'] = spec.make_init()
                namespace['close'] = spec.make_close()
                if spec.enter is not None:
                    namespace['__enter__'] = spec.make_enter()
                if spec.exit is not None:
                    namespace['__exit__'] = spec.make_exit()
                break
        cls = super().__new__(mcs, name, bases, namespace)
        return cls


class ObjectBase(metaclass=ObjectBaseMeta):

    Spec = Spec
