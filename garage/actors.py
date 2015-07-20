"""A minimum implementation of the actor model."""

__all__ = [
    'BUILD',
    'ActorError',
    'Stub',
    'build',
    'method',
]

import collections
import functools
import queue
import threading
import types
from concurrent.futures import Future


BUILD = object()


_MAGIC = object()


class ActorError(Exception):
    pass


def method(func):
    """Decorate a func as a method of an actor."""
    if not isinstance(func, types.FunctionType):
        raise ActorError('%r is not a function' % func)
    func.is_actor_method = _MAGIC
    return func


class _StubMeta(type):
    """Generates a stub class when given an actor class."""

    def __new__(mcs, name, bases, namespace, actor=None):
        if actor:
            stub_methods = _StubMeta.make_stub_methods(actor)
            for stub_method_name in stub_methods:
                if stub_method_name in namespace:
                    raise ActorError(
                        'stub method should not override %s.%s' %
                        (name, stub_method_name))
                namespace[stub_method_name] = stub_methods[stub_method_name]
        cls = super().__new__(mcs, name, bases, namespace)
        if actor:
            Stub.actors[cls] = actor
        return cls

    def __init__(cls, name, bases, namespace, **_):
        super().__init__(name, bases, namespace)

    @staticmethod
    def make_stub_methods(actor_class):
        stub_methods = {}
        for cls in actor_class.__mro__:
            for name, func in vars(cls).items():
                if not hasattr(func, 'is_actor_method'):
                    continue
                if func.is_actor_method is not _MAGIC:
                    raise ActorError(
                        'function should not overwrite %s.is_actor_method',
                        func.__qualname__)
                if name not in stub_methods:
                    stub_methods[name] = _StubMeta.make_stub_method(func)
        return stub_methods

    @staticmethod
    def make_stub_method(func):
        @functools.wraps(func)
        def stub_method(self, *args, **kwargs):
            return Stub.send_message(self, func, args, kwargs)
        return stub_method


def build(stub_cls, *, name=None, maxsize=0, args=None, kwargs=None):
    return stub_cls(
        BUILD,
        name=name,
        maxsize=maxsize,
        args=args or (),
        kwargs=kwargs or {},
    )


class Stub(metaclass=_StubMeta):
    """The base class of all actor stub classes."""

    actors = {}

    #
    # NOTE:
    #
    # * _StubMeta may generate stub methods for a subclass that
    #   override Stub's methods.  Always use fully qualified name
    #   when calling Stub's methods.
    #
    # * Subclass field names might conflict Stub's.  Always use
    #   double leading underscore (and thus enable name mangling) on
    #   Stub's fields.
    #
    # * We don't join threads.
    #   TODO: Make sure this won't result in memory leak.
    #

    def __init__(self, *args, **kwargs):
        cls = Stub.actors.get(type(self))
        if not cls:
            raise ActorError(
                '%s is not a stub of an actor' % type(self).__qualname__)
        if args and args[0] is BUILD:
            name = kwargs.get('name')
            maxsize = kwargs.get('maxsize', 0)
            args = kwargs.get('args', ())
            kwargs = kwargs.get('kwargs', {})
        else:
            name = None
            maxsize = 0
            # Should I make a copy of args and kwargs?
            args = tuple(args)
            kwargs = dict(kwargs)
        self.__work_queue = queue.Queue(maxsize=maxsize)
        self.__dead = threading.Event()
        threading.Thread(
            target=_actor_message_loop,
            name=name,
            args=(self.__work_queue, self.__dead),
            daemon=True,
        ).start()
        # Since we can't return a future here, we have to wait on the
        # result of actor's __init__() call for any exception that might
        # be raised inside it.
        Stub.send_message(self, cls, args, kwargs).result()

    def is_dead(self):
        return self.__dead.is_set()

    def send_message(self, func, args, kwargs):
        if Stub.is_dead(self):
            raise ActorError('actor is dead')
        future = Future()
        self.__work_queue.put(_Work(future, func, args, kwargs))
        return future


_Work = collections.namedtuple('_Work', 'future func args kwargs')


def _actor_message_loop(work_queue, dead):
    """The main message processing loop of an actor."""
    try:
        _actor_message_loop_impl(work_queue)
    finally:
        dead.set()


def _actor_message_loop_impl(work_queue):
    # NOTE: `del work` as soon as possible (see issue 16284).

    # The first message must be the __init__() call.
    work = work_queue.get()
    assert work.future.set_running_or_notify_cancel()
    try:
        actor = work.func(*work.args, **work.kwargs)
    except BaseException as exc:
        work.future.set_exception(exc)
        return  # Terminate the actor thread.
    else:
        work.future.set_result(actor)
    work_queue.task_done()
    del work

    while True:
        work = work_queue.get()
        if not work.future.set_running_or_notify_cancel():
            work_queue.task_done()
            del work
            continue

        try:
            result = work.func(actor, *work.args, **work.kwargs)
        except BaseException as exc:
            work.future.set_exception(exc)
            return  # Terminate the actor thread.
        else:
            work.future.set_result(result)
        work_queue.task_done()
        del work
