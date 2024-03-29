"""Actors.

An actor is just a function running in a thread that processes messages
from a queue, and you interact with an actor through a stub object.

A few kinds of actor are implemented here:

* Object-based actor that interprets messages as method calls of the
  object bound to this actor.

* Function-calling actor that interprets messages as function calls.

If these do not fit your need, you can always create your actor since it
is just a function.
"""

__all__ = [
    'MethodCall',
    'Stub',
    'from_object',
    'function_caller',
]

import functools
import logging
import threading
import typing

from g1.bases import classes
from g1.bases.assertions import ASSERT
from g1.bases.collections import Namespace

from . import futures
from . import queues

LOG = logging.getLogger(__name__)

NON_GRACE_PERIOD = 0.1  # Unit: seconds.


def from_object(obj, **kwargs):
    """Make a object-based actor."""
    return Stub(
        actor=make_method_caller(obj),
        method_names=classes.get_public_method_names(obj),
        **kwargs,
    )


class Stub:
    """Stub for interacting with an actor."""

    def __init__(
        self,
        *,
        actor,
        method_names=(),
        queue=None,
        name=None,
        daemon=None,
    ):
        self.future = futures.Future()
        self.queue = queue if queue is not None else queues.Queue()

        # Create method senders for convenience.
        if method_names:
            self.m = make_senders(method_names, self.queue)

        self._thread = threading.Thread(
            target=futures.wrap_thread_target(actor, self.future),
            name=name,
            args=(self.queue, ),
            daemon=daemon,
        )
        self._thread.start()

    __repr__ = classes.make_repr('{self._thread!r}')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        graceful = not exc_type
        self.shutdown(graceful)
        try:
            self.join(None if graceful else NON_GRACE_PERIOD)
        except futures.Timeout:
            LOG.warning('actor join timeout: %r', self)

    def shutdown(self, graceful=True):
        items = self.queue.close(graceful)
        if items:
            LOG.warning('drop %d messages', len(items))
        return items

    def join(self, timeout=None):
        exc = self.future.get_exception(timeout)
        if exc:
            LOG.error('actor crash: %r', self, exc_info=exc)


class MethodCall(typing.NamedTuple):
    """Message type for object-based actor and function-calling actor."""
    method: typing.Union[str, typing.Callable]
    args: tuple
    kwargs: dict
    future: futures.Future


def make_senders(method_names, queue):
    entries = {name: _make_sender(name, queue) for name in method_names}
    return Namespace(**entries)


def _make_sender(name, queue):

    def sender(*args, **kwargs):
        future = futures.Future()
        call = MethodCall(method=name, args=args, kwargs=kwargs, future=future)
        queue.put(call)
        return future

    return sender


#
# Object-based actor.
#


def make_method_caller(obj):
    """Make a ``method_caller`` actor."""
    return functools.partial(method_caller, obj)


def method_caller(obj, queue):
    """Actor that interprets messages as method calls of an object."""
    LOG.debug('start')
    while True:
        try:
            call = ASSERT.isinstance(queue.get(), MethodCall)
        except queues.Closed:
            break
        with call.future.catching_exception(reraise=False):
            method = getattr(obj, ASSERT.isinstance(call.method, str))
            call.future.set_result(method(*call.args, **call.kwargs))
        del call
    LOG.debug('exit')


#
# Function-calling actor.
#


def function_caller(queue):
    """Actor that interprets messages as function calls."""
    LOG.debug('start')
    while True:
        try:
            call = ASSERT.isinstance(queue.get(), MethodCall)
        except queues.Closed:
            break
        with call.future.catching_exception(reraise=False):
            ASSERT.predicate(call.method, callable)
            call.future.set_result(call.method(*call.args, **call.kwargs))
        del call
    LOG.debug('exit')
