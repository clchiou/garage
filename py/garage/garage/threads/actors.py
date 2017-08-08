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

An actor and the world communicate with each other through a queue and a
future object.

Queue: (world -> actor)

  * The world sends messages to the actor through the queue, obviously.

  * The world, or sometimes the actor itself, signals a kill of the
    actor by closing the queue (but the actor won't die immediately).

Future object: (actor -> world)

  * When the actor is about to die, it completes the future object.
    And thus the world may know when an actor was died by observing the
    future object.

  * Note that, an actor could be dead without the world killing it (when
    an message raises an uncaught exception, for example).

"""

__all__ = [
    'BUILD',
    'ActorError',
    'Exit',
    'Exited',
    'Return',
    'OneShotActor',
    'Stub',
    'method',
    'build',
    'make_maker',
    'inject',
]

import collections
import functools
import logging
import threading
import types
import weakref
from concurrent.futures import Future

from garage import asserts

from . import queues
from . import utils


LOG = logging.getLogger(__name__)


BUILD = object()


_MAGIC = object()


class ActorError(Exception):
    """A generic error of actors."""


class Exited(ActorError):
    """Raise when sending message to an exited actor."""


class Exit(Exception):
    """Raise this when an actor would like to self-terminate."""


class Return(Exception):
    """Request to append a message to the actor's own queue."""

    def __init__(self, result, func, *args, **kwargs):
        self.result = result
        self.message_data = (func, args, kwargs)


class OneShotActor:
    """A special kind of actor that processes one type of message and
    processes one message only (but I would prefer not to use metaclass
    in this simpler case).
    """

    @classmethod
    def from_func(cls, actor_func):
        stub_maker = cls(actor_func)
        names = utils.generate_names(name=actor_func.__name__)
        def make(*args, **kwargs):
            return build(
                stub_maker,
                name=next(names),
                set_pthread_name=True,
                args=args,
                kwargs=kwargs,
            )
        # Create an alias to the exposed member
        make.actor_func = stub_maker.actor_func
        return make

    class Stub:

        def __init__(self, name, future):
            self._name = name  # Because Stub exposes this
            self._future = future

        def _kill(self, graceful=True):
            self._future.cancel()

        def _get_future(self):
            return self._future

        def _send_message(self, func, args, kwargs, block=True, timeout=None):
            raise Exited('OneShotActor does not take additional message')

    def __init__(self, actor_func):
        self.actor_func = actor_func

    def __call__(self, *args, **kwargs):
        if args and args[0] is BUILD:
            name = kwargs.get('name')
            set_pthread_name = kwargs.get('set_pthread_name')
            args = kwargs.get('args', ())
            kwargs = kwargs.get('kwargs', {})
        else:
            name = None
            set_pthread_name = False
        future = Future()
        thread = threading.Thread(
            target=self._run_actor,
            name=name,
            args=(weakref.ref(future), args, kwargs),
            daemon=True,
        )
        thread.start()
        # thread.ident is None if it has not been started
        if set_pthread_name:
            utils.set_pthread_name(thread, name)
        # Let interface be consistent with full-blown actors
        return self.Stub(thread.name, future)

    def _run_actor(self, future_ref, args, kwargs):
        if not _deref(future_ref).set_running_or_notify_cancel():
            return
        LOG.debug('start')
        try:
            result = self.actor_func(*args, **kwargs)
        except BaseException as exc:
            _deref(future_ref).set_exception(exc)
        else:
            _deref(future_ref).set_result(result)
        LOG.debug('exit')


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
                if stub_method_name.startswith('_'):
                    raise ActorError(
                        'stub method name starts with "_": %s.%s' %
                        (name, stub_method_name))
                if stub_method_name in namespace:
                    raise ActorError(
                        'stub method should not override %s.%s' %
                        (name, stub_method_name))
                namespace[stub_method_name] = stub_methods[stub_method_name]
        stub_cls = super().__new__(mcs, name, bases, namespace)
        if actor:
            Stub.ACTORS[stub_cls] = actor
        return stub_cls

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
            return self._send_message(func, args, kwargs)
        return stub_method


def build(stub_cls, *,
          name=None, set_pthread_name=False,
          capacity=0,
          args=None, kwargs=None):
    """Build a stub/actor pair with finer configurations."""
    return stub_cls(
        BUILD,
        name=name, set_pthread_name=set_pthread_name,
        capacity=capacity,
        args=args or (), kwargs=kwargs or {},
    )


def make_maker(basename, capacity=0):
    """Return a default classmethod `make` that wraps `build`."""

    names = names = utils.generate_names(name=basename)

    @classmethod
    def make(cls, *args, **kwargs):
        return build(
            cls,
            name=next(names), set_pthread_name=True,
            capacity=capacity,
            args=args, kwargs=kwargs,
        )

    return make


def inject(args, kwargs, extra_args=None, extra_kwargs=None):
    """Inject additional args/kwargs into the args/kwargs that will be
       sent to the actor.

       In order to support build(), Stub.__init__ method's signature is
       slightly more complex than you might expect.  If you would like
       to override Stub.__init__, use this function to inject additional
       args/kwargs that you would like to send to the actor's __init__.

       You may use this to pass the stub object to the actor, but bear
       in mind that this might cause unnecessary object retention.
    """
    if args and args[0] is BUILD:
        if extra_args:
            kwargs['args'] += extra_args
        if extra_kwargs:
            kwargs['kwargs'].update(extra_kwargs)
    else:
        if extra_args:
            args += extra_args
        if extra_kwargs:
            kwargs.update(extra_kwargs)
    return args, kwargs


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
    # * We don't join threads; instead, wait on the future object.
    #

    def __init__(self, *args, **kwargs):
        """Start the actor thread, and then block on actor object's
           __init__ and re-raise the exception if it fails."""
        actor_cls = Stub.ACTORS.get(type(self))
        if not actor_cls:
            raise ActorError(
                '%s is not a stub of an actor' % type(self).__qualname__)
        if args and args[0] is BUILD:
            name = kwargs.get('name')
            set_pthread_name = kwargs.get('set_pthread_name')
            capacity = kwargs.get('capacity', 0)
            args = kwargs.get('args', ())
            kwargs = kwargs.get('kwargs', {})
        else:
            name = None
            set_pthread_name = False
            capacity = 0
        self.__msg_queue = queues.Queue(capacity=capacity)
        self.__future = Future()
        thread = threading.Thread(
            target=_actor_message_loop,
            name=name,
            args=(self.__msg_queue, weakref.ref(self.__future)),
            daemon=True,
        )
        self._name = thread.name  # Useful for logging
        thread.start()
        # Since we can't return a future here, we have to wait on the
        # result of actor's __init__() call for any exception that might
        # be raised inside it.  (By the way, use Stub._send_message here
        # to ensure that we won't call sub-class' _send_message.)
        Stub._send_message(self, actor_cls, args, kwargs).result()
        # If this stub is not referenced, kill the actor gracefully.
        weakref.finalize(self, self.__msg_queue.close)
        if set_pthread_name:
            utils.set_pthread_name(thread, name)

    def _kill(self, graceful=True):
        """Set the kill flag of the actor thread.

           If graceful is True (the default), the actor will be dead
           after it processes the remaining messages in the queue.
           Otherwise it will be dead after it finishes processing the
           current message.

           Note that this method does not block even when the queue is
           full (in other words, you can't implement kill on top of the
           normal message sending without the possibility that caller
           being blocked).
        """
        for msg in self.__msg_queue.close(graceful=graceful):
            _deref(msg.future_ref).cancel()

    def _get_future(self):
        """Return the future object that represents actor's liveness.

           Note: Cancelling this future object is not going to kill this
           actor.  You should call kill() instead.
        """
        return self.__future

    def _send_message(self, func, args, kwargs, block=True, timeout=None):
        """Enqueue a message into actor's message queue."""
        try:
            future = Future()
            self.__msg_queue.put(
                _Message(weakref.ref(future), func, args, kwargs),
                block=block,
                timeout=timeout,
            )
            return future
        except queues.Closed:
            raise Exited('actor has been killed') from None


_Message = collections.namedtuple('_Message', 'future_ref func args kwargs')


class _FakeFuture:

    def cancel(self):
        return True

    def set_running_or_notify_cancel(self):
        return True

    def set_result(self, _):
        pass

    def set_exception(self, _):
        pass


_FAKE_FUTURE = _FakeFuture()


def _deref(ref):
    """Dereference a weak reference of future."""
    obj = ref()
    return obj if obj is not None else _FAKE_FUTURE


def _actor_message_loop(msg_queue, future_ref):
    """The main message processing loop of an actor."""
    LOG.debug('start')
    try:
        _actor_message_loop_impl(msg_queue, future_ref)
    except Exit:
        for msg in msg_queue.close(graceful=False):
            _deref(msg.future_ref).cancel()
        _deref(future_ref).set_result(None)
    except BaseException as exc:
        for msg in msg_queue.close(graceful=False):
            _deref(msg.future_ref).cancel()
        _deref(future_ref).set_exception(exc)
    else:
        asserts.true(msg_queue.is_closed())
        _deref(future_ref).set_result(None)
    LOG.debug('exit')


def _actor_message_loop_impl(msg_queue, future_ref):
    """Dequeue and process messages one by one."""
    # Note: Call `del msg` as soon as possible (see issue 16284).

    if not _deref(future_ref).set_running_or_notify_cancel():
        raise ActorError('future of this actor has been canceled')

    # The first message must be the __init__() call.
    msg = msg_queue.get()
    if not _deref(msg.future_ref).set_running_or_notify_cancel():
        raise ActorError('__init__ has been canceled')

    try:
        actor = msg.func(*msg.args, **msg.kwargs)
    except BaseException as exc:
        _deref(msg.future_ref).set_exception(exc)
        raise
    else:
        _deref(msg.future_ref).set_result(actor)
    del msg

    LOG.debug('start message loop')
    while True:
        try:
            msg = msg_queue.get()
        except queues.Closed:
            break

        if not _deref(msg.future_ref).set_running_or_notify_cancel():
            del msg
            continue

        try:
            result = msg.func(actor, *msg.args, **msg.kwargs)
        except Return as ret:
            _deref(msg.future_ref).set_result(ret.result)
            try:
                msg_queue.put(
                    # Use `lambda: None` as a fake weakref
                    _Message(lambda: None, *ret.message_data),
                    # Do not block the message loop inside itself
                    block=False,
                )
            except (queues.Closed, queues.Full) as exc:
                # I am not sure if I should notify the original method
                # caller about this error, nor if I should break this
                # actor message loop.  For now let's just log the error
                # and carry on.
                LOG.error('cannot append message %r due to %r',
                          ret.message_data, exc)
        except BaseException as exc:
            _deref(msg.future_ref).set_exception(exc)
            raise
        else:
            _deref(msg.future_ref).set_result(result)
        del msg


#
# Observe that stubs return a Future object of method result (let's call
# this the result Future object).  An interesting idea is that, if a
# method returns a Future object X, instead of put it inside the result
# Future object R, thus a future of future, we could add R's callback to
# X.  So when X is done, R's callback will be called, and so R will be
# done, too.  For example,
#
#    class _Alice:
#        @actors.method
#        def compute(self):
#            # Forward long computation to another actor Bob.
#            return self.other_stub.do_long_computation()
#
#    class _Bob:
#        @actors.method
#        def do_long_computation(self):
#            time.sleep(60)  # Simulate a long computation.
#            return 42
#
# So under this idea, we will write
#
#    stub.compute().result() == 42
#
# rather than
#
#    stub.compute().result().result() == 42
#
# Essentially, this makes Bob invisible from an outside observer.
#
#
# This idea, let's call it "future chaining" for now, while sounds
# interesting, has a few issues that I haven't sorted out yet; so I
# will leave the notes here for future reference.
#
# First, the current mental model is that an actor will process messages
# one by one sequentially.  Nevertheless, under the future chaining, we
# will have Alice returned immediately from compute() while Bob is still
# processing do_long_computation().  Then Alice will start processing
# the next message.  From an outside observer, it is as if the first and
# the second message were being processed concurrently instead of
# sequentially (and the second message could be done before the first
# one, which makes things even more confusing).
#
# Second, since all the callbacks are called by the innermost actor
# thread (Bob), while it is easy to propagate the result (42) to all the
# chained Future objects, it is difficulty to propagate and re-raise
# exceptions to all the outer actor threads to kill them properly.
# Imagine while Bob is processing do_long_computation(), it raises an
# exception.  Now not only Bob but also Alice should be dead because
# under the future chaining, Bob is invisible from an outside observer,
# and the observer could only observe that Alice's compute() has raised
# an exception, deducing that Alice should be dead after that.
#
