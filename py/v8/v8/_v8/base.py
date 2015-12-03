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

    def __init__(
            self, *,
            name,
            ctor, dtor,
            enter=None, exit=None,
            extra=None,
            level=logging.DEBUG):
        self.name = name
        self.ctor = ctor
        self.dtor = dtor
        self.enter = enter
        self.exit = exit
        self.extra = extra
        self.level = level


class ObjectBaseMeta(type):

    def __new__(mcs, name, bases, namespace):
        for spec in namespace.values():
            if isinstance(spec, Spec):
                LOG.debug('add wrapper methods to %s', name)
                ObjectBaseMeta.add_methods(spec, namespace)
                break
        cls = super().__new__(mcs, name, bases, namespace)
        return cls

    @staticmethod
    def add_methods(spec, namespace):
        namespace['__init__'] = ObjectBaseMeta.make_init(spec)
        namespace['close'] = ObjectBaseMeta.make_close(spec)
        if spec.enter is not None:
            namespace['__enter__'] = ObjectBaseMeta.make_enter(spec)
        if spec.exit is not None:
            namespace['__exit__'] = ObjectBaseMeta.make_exit(spec)

    @staticmethod
    def make_init(spec):
        if spec.extra:
            names = [spec.name] + spec.extra
            def __init__(self, *args):
                LOG.log(spec.level, 'new %s', spec.name)
                self.__dict__.update(zip(
                    names,
                    map(not_null, spec.ctor(*args)),
                ))
        else:
            def __init__(self, *args):
                LOG.log(spec.level, 'new %s', spec.name)
                self.__dict__[spec.name] = not_null(spec.ctor(*args))
        return __init__

    @staticmethod
    def make_close(spec):
        def close(self):
            LOG.log(spec.level, 'delete %s', spec.name)
            spec.dtor(self.__dict__.pop(spec.name))
        return close

    @staticmethod
    def make_enter(spec):
        def __enter__(self):
            LOG.log(spec.level, 'enter %s', spec.name)
            obj = self.__dict__[spec.name]
            spec.enter(obj)
            return obj
        return __enter__

    @staticmethod
    def make_exit(spec):
        def __exit__(self, *_):
            LOG.log(spec.level, 'exit %s', spec.name)
            spec.exit(self.__dict__[spec.name])
        return __exit__


class ObjectBase(metaclass=ObjectBaseMeta):

    Spec = Spec

    def close(self):
        raise AssertionError(
            '%s.close() is undefined' % self.__class__.__name__)
