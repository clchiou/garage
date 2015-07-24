"""A minimum implementation of the actor model.

An actor is basically a daemon thread processing messages from a queue,
and a message is composed of a method and its arguments (you can think
of it as a single-threaded executor).

By default the queue size is infinite, but you may specify a finite
queue size, which is useful in implementing back pressure.

An actor's state is either alive or dead, and once it's dead, it will
never become alive again (but even if it is alive at this moment, it
does not guarantee that it will still be alive at the next moment).

Since actors are executed by daemon threads, when the main program
exits, all actor threads might not have chance to release resources,
which typically are calling __exit__ in context managers.  So you should
pay special attention to resources that must be release even when the
main program is crashing (unlike ThreadPoolExecutor, which blocks the
main program until all submitted jobs are done).
"""

__all__ = [
    'BUILD',
    'ActorError',
    'Stub',
    'build',
    'method',
]

import collections
import functools
import logging
import queue
import threading
import types
from concurrent.futures import Future


BUILD = object()


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


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
            Stub.ACTORS[cls] = actor
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

    # Map stub classes to their actor class.
    ACTORS = {}

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
    #

    def __init__(self, *args, **kwargs):
        """Start the actor thread, and then block on actor object's
           __init__ and re-raise the exception if it fails."""
        cls = Stub.ACTORS.get(type(self))
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
        self.__kill_graceful = threading.Event()
        self.__kill = threading.Event()
        self.__dead = threading.Event()
        threading.Thread(
            target=_actor_message_loop,
            name=name,
            args=(self.__work_queue,
                  self.__kill_graceful,
                  self.__kill,
                  self.__dead),
            daemon=True,
        ).start()
        # Since we can't return a future here, we have to wait on the
        # result of actor's __init__() call for any exception that might
        # be raised inside it.
        Stub.send_message(self, cls, args, kwargs).result()

    def kill(self, graceful=True):
        """Set the kill flag of the actor thread.

           If graceful is True (the default), the actor will be dead
           until it processes the remaining messages in the queue.
           Otherwise it will be dead after it finishes processing the
           current message.

           Note that this method does not block even when the queue is
           full (in other words, you can't implement kill on top of the
           normal message sending without the possibility that caller
           being blocked).
        """
        self.__kill_graceful.set()
        if not graceful:
            self.__kill.set()

    def is_dead(self):
        """True if the actor thread has exited."""
        return self.__dead.is_set()

    def wait(self, timeout=None):
        """Wait until is_dead flag is set."""
        return self.__dead.wait(timeout)

    def send_message(self, func, args, kwargs, block=True, timeout=None):
        """Enqueue a message into actor's message queue."""
        if self.__kill_graceful.is_set():
            raise ActorError('actor is being killed')
        # Even if is_dead() returns False, there is no guarantee that
        # the actor will process this message.  But there is no harm to
        # check here.
        if Stub.is_dead(self):
            raise ActorError('actor is dead')
        future = Future()
        self.__work_queue.put(
            _Work(future, func, args, kwargs),
            block=block,
            timeout=timeout,
        )
        return future


_Work = collections.namedtuple('_Work', 'future func args kwargs')


def _actor_message_loop(work_queue, kill_graceful, kill, dead):
    """The main message processing loop of an actor."""
    try:
        _actor_message_loop_impl(work_queue, kill_graceful, kill)
    except BaseException:
        LOG.error('unexpected error inside actor thread', exc_info=True)
    finally:
        dead.set()


def _actor_message_loop_impl(work_queue, kill_graceful, kill):
    """Dequeue and process messages one by one."""
    #
    # NOTE:
    #
    # * Call `del work` as soon as possible (see issue 16284).
    #
    # * Don't have to call task_done() since we don't join on the queue.
    #

    # The first message must be the __init__() call.
    work = work_queue.get()
    assert work.future.set_running_or_notify_cancel()
    try:
        actor = work.func(*work.args, **work.kwargs)
    except BaseException as exc:
        work.future.set_exception(exc)
        return
    else:
        work.future.set_result(actor)
    del work

    while not (kill.is_set() or
               kill_graceful.is_set() and work_queue.empty()):
        # XXX: Do polling with timeout so that we may receive kill
        # signals; is there a better solution?
        try:
            work = work_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        if not work.future.set_running_or_notify_cancel():
            del work
            continue

        try:
            result = work.func(actor, *work.args, **work.kwargs)
        except BaseException as exc:
            work.future.set_exception(exc)
            return
        else:
            work.future.set_result(result)
        del work
