"""Resource pools."""

__all__ = [
    'ProcessActorPool',
    'TimeoutPool',
]

import collections
import contextlib
import dataclasses
import functools
import heapq
import inspect
import itertools
import logging
import multiprocessing
import os
import pickle
import threading
import time
import types
import weakref
from typing import Any, Dict, Tuple

from . import collections as g1_collections  # pylint: disable=reimported
from .assertions import ASSERT

LOG = logging.getLogger(__name__)


class TimeoutPool:
    """Rudimentary timeout-based resource pool.

    A pool that releases resources unused after a timeout.

    NOTE: This class is not thread-safe.
    """

    @dataclasses.dataclass(frozen=True)
    class Stats:
        num_allocations: int
        num_concurrent_resources: int
        max_concurrent_resources: int

    def __init__(
        self,
        pool_size,
        allocate,
        release,
        timeout=300,  # 5 minutes.
    ):
        # Store pairs of (resource, returned_at), sorted by returned_at
        # in ascending order.
        self._pool = collections.deque()
        self._pool_size = pool_size
        self._allocate = allocate
        self._release = release
        self._timeout = timeout
        self._num_allocations = 0
        self._num_concurrent_resources = 0
        self._max_concurrent_resources = 0

    def get_stats(self):
        return self.Stats(
            num_allocations=self._num_allocations,
            num_concurrent_resources=self._num_concurrent_resources,
            max_concurrent_resources=self._max_concurrent_resources,
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @contextlib.contextmanager
    def using(self):
        resource = self.get()
        try:
            yield resource
        finally:
            self.return_(resource)

    def get(self):
        """Get a resource from the pool or allocate new one when empty.

        This does not block nor raise when the pool is empty (if we want
        to implement rate limit, we could do that?).
        """
        to_allocate = not self._pool
        if to_allocate:
            resource = self._allocate()
            self._num_allocations += 1
            self._num_concurrent_resources += 1
            max_concurrent_resources = max(
                self._num_concurrent_resources, self._max_concurrent_resources
            )
        else:
            # Return the most recently released resource so that the
            # less recently released resources may grow older and then
            # released eventually.
            resource = self._pool.pop()[0]
            max_concurrent_resources = self._max_concurrent_resources
        try:
            self.cleanup()
        except Exception:
            if to_allocate:
                self._num_allocations -= 1
                self._num_concurrent_resources -= 1
            self._release(resource)
            raise
        self._max_concurrent_resources = max_concurrent_resources
        return resource

    def return_(self, resource):
        """Return the resource to the pool.

        The pool will release resources for resources that exceed the
        timeout, or when the pool is full.
        """
        now = time.monotonic()
        self._pool.append((resource, now))
        self._cleanup(now)

    def cleanup(self):
        """Release resources that exceed the timeout.

        You may call this periodically to release old resources so that
        pooled resources is not always at high water mark.  Note that
        get/return_ calls this for you; so if the program uses the pool
        frequently, you do not need to call cleanup periodically.
        """
        self._cleanup(time.monotonic())

    def _cleanup(self, now):
        deadline = now - self._timeout
        while self._pool:
            if (
                len(self._pool) > self._pool_size
                or self._pool[0][1] < deadline
            ):
                self._release_least_recently_released_resource()
            else:
                break

    def close(self):
        """Release all resources in the pool."""
        while self._pool:
            self._release_least_recently_released_resource()

    def _release_least_recently_released_resource(self):
        self._num_concurrent_resources -= 1
        self._release(self._pool.popleft()[0])


class ProcessActorPool:
    """Process-actor pool.

    stdlib's multiprocessing.pool.Pool is modeled after the executor
    where workers are stateless.  ProcessActorPool manages a pool of
    stateful process-actors.

    If an actor is not returned to the pool and is garbage collected,
    the associated process and other resources will be automatically
    returned to the pool or released.

    NOTE: This class is not thread-safe.
    """

    @dataclasses.dataclass(frozen=True)
    class Stats:
        num_spawns: int
        num_concurrent_processes: int
        max_concurrent_processes: int
        current_highest_uses: int

    _COUNTER = itertools.count(1).__next__

    @dataclasses.dataclass(order=True)
    class _Entry:
        process: multiprocessing.Process = dataclasses.field(compare=False)
        input_queue: multiprocessing.SimpleQueue = \
            dataclasses.field(compare=False)
        output_queue: multiprocessing.SimpleQueue = \
            dataclasses.field(compare=False)
        negative_num_uses: int

    def __init__(self, pool_size, max_uses_per_actor=None, context=None):
        # Store processes, sorted by num_uses in descending order.
        self._pool = []
        self._pool_size = pool_size
        # Store id(actor) -> entry.  We store id(actor) to avoid
        # creating a strong reference to the actor.
        self._actor_ids_in_use = {}
        self._max_uses_per_actor = max_uses_per_actor
        self._context = context or multiprocessing.get_context()
        self._num_spawns = 0
        self._num_concurrent_processes = 0
        self._max_concurrent_processes = 0

    def get_stats(self):
        if self._pool:
            current_highest_uses = -self._pool[0].negative_num_uses
        else:
            current_highest_uses = 0
        for entry in self._actor_ids_in_use.values():
            num_uses = -entry.negative_num_uses
            if num_uses > current_highest_uses:
                current_highest_uses = num_uses
        return self.Stats(
            num_spawns=self._num_spawns,
            num_concurrent_processes=self._num_concurrent_processes,
            max_concurrent_processes=self._max_concurrent_processes,
            current_highest_uses=current_highest_uses,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        self.close(graceful=not exc_type)

    @contextlib.contextmanager
    def using(self, referent):
        actor = self.get(referent)
        try:
            yield actor
        finally:
            self.return_(actor)

    def get(self, referent):
        """Get an actor from the pool or allocate new one when empty.

        This does not block nor raise when the pool is empty (if we want
        to implement rate limit, we could do that?).
        """
        to_spawn = not self._pool
        if to_spawn:
            entry = self._spawn()
            self._num_spawns += 1
            self._num_concurrent_processes += 1
            max_concurrent_processes = max(
                self._num_concurrent_processes, self._max_concurrent_processes
            )
        else:
            # Return the most often used process so that is will be
            # released sooner (when max_uses_per_actor is set).
            entry = heapq.heappop(self._pool)
            max_concurrent_processes = self._max_concurrent_processes

        actor = _ActorStub(
            referent, entry.process, entry.input_queue, entry.output_queue
        )
        actor_id = id(actor)

        try:
            # Although this actor_id can be the same as another already
            # collected actor's id (since id is just object's address),
            # it is very unlikely that this id conflict will happen when
            # the entry is still in the self._actor_ids_in_use dict as
            # it requires all these to happen:
            #
            # * The old actor is collected.
            # * The old actor's finalizer has not been called yet (is
            #   this even possible?).
            # * The new actor is allocated, at the same address.
            #
            # But there is not harm to assert this will never happen.
            ASSERT.setitem(self._actor_ids_in_use, actor_id, entry)

            _MethodStub(\
                '__init__', entry.input_queue, entry.output_queue
            )(referent)
            self._cleanup()
        except Exception:
            if to_spawn:
                self._num_spawns -= 1
                # self._num_concurrent_processes is decreased in
                # self._release.
            self._actor_ids_in_use.pop(actor_id)
            self._release(entry)
            raise

        weakref.finalize(actor, self._return_id, actor_id)
        entry.negative_num_uses -= 1
        self._max_concurrent_processes = max_concurrent_processes
        return actor

    def return_(self, actor):
        """Return the actor to the pool.

        The pool will release actors for actors that exceed the
        ``max_uses_per_actor``, or when the pool is full.
        """
        return self._return_id(id(actor))

    def _return_id(self, actor_id):
        entry = self._actor_ids_in_use.pop(actor_id, None)
        if entry is None:
            return
        try:
            _MethodStub('__del__', entry.input_queue, entry.output_queue)()
        except Exception:
            self._release(entry)
            raise
        heapq.heappush(self._pool, entry)
        self._cleanup()

    def _spawn(self):
        input_queue = self._context.SimpleQueue()
        output_queue = self._context.SimpleQueue()

        name = 'pactor-%02d' % self._COUNTER()
        entry = self._Entry(
            process=self._context.Process(
                name=name,
                target=_process_actor,
                args=(name, input_queue, output_queue),
            ),
            input_queue=input_queue,
            output_queue=output_queue,
            negative_num_uses=0,
        )
        entry.process.start()

        return entry

    def _release(self, entry):
        self._num_concurrent_processes -= 1

        try:
            entry.input_queue.put(None)
            entry.process.join(timeout=1)
            if entry.process.exitcode is None:
                LOG.warning(
                    'process actor does not quit: pid=%d', entry.process.pid
                )
                entry.process.kill()
                entry.process.join(timeout=1)
                if entry.process.exitcode is None:
                    raise RuntimeError(
                        'process actor cannot be killed: pid=%d' %
                        entry.process.pid
                    )

            if entry.process.exitcode != 0:
                # Sadly SIGTERM also causes exitcode != 0.
                LOG.warning(
                    'process actor err out: pid=%d exitcode=%d',
                    entry.process.pid,
                    entry.process.exitcode,
                )

            # Process can only be closed after exits.
            entry.process.close()

        finally:
            entry.input_queue._reader.close()
            entry.input_queue._writer.close()
            entry.output_queue._reader.close()
            entry.output_queue._writer.close()

    def _cleanup(self):
        while self._pool:
            if (
                len(self._pool) > self._pool_size or (
                    self._max_uses_per_actor is not None and
                    -self._pool[0].negative_num_uses > self._max_uses_per_actor
                )
            ):
                self._release(heapq.heappop(self._pool))
            else:
                break
        # Check crashed actors.
        i = 0
        last = len(self._pool) - 1
        while i <= last:
            if self._pool[i].process.exitcode is not None:
                self._pool[i], self._pool[last] = \
                    self._pool[last], self._pool[i]
                last -= 1
            else:
                i += 1
        if last < len(self._pool) - 1:
            to_release = self._pool[last:]
            del self._pool[last:]
            heapq.heapify(self._pool)
            for entry in to_release:
                try:
                    self._release(entry)
                except Exception as exc:
                    LOG.error('cleanup: unable to release process: %r', exc)

    def close(self, graceful=True):
        entries = list(self._pool)
        self._pool.clear()

        if graceful:
            for entry in entries:
                try:
                    self._release(entry)
                except Exception as exc:
                    LOG.error('close: unable to release process: %r', exc)
            ASSERT.empty(self._actor_ids_in_use)

        else:
            entries.extend(self._actor_ids_in_use.values())
            self._actor_ids_in_use.clear()
            self._num_concurrent_processes -= len(entries)
            for entry in entries:
                entry.process.kill()
            for entry in entries:
                entry.process.join(timeout=1)
                if entry.process.exitcode is None:
                    LOG.error(
                        'close: process actor cannot be killed: pid=%d',
                        entry.process.pid
                    )
                else:
                    # Process can only be closed after exits.
                    entry.process.close()
                entry.input_queue._reader.close()
                entry.input_queue._writer.close()
                entry.output_queue._reader.close()
                entry.output_queue._writer.close()


@dataclasses.dataclass(frozen=True)
class _Call:
    method: str
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]


class _ActorStub:

    def __init__(self, referent, process, input_queue, output_queue):
        self._referent_type = type(referent)
        self._process = process
        self._method_stubs = g1_collections.LoadingDict(
            functools.partial(
                _MethodStub,
                input_queue=input_queue,
                output_queue=output_queue,
            )
        )

    def __getattr__(self, name):
        ASSERT.none(self._process.exitcode)
        attr = getattr(self._referent_type, name, None)
        stub = self._method_stubs[ASSERT.not_startswith(name, '_')]
        if attr is None or isinstance(attr, property):
            # Instance attribute or property.
            return stub()
        else:
            # Static/class/instance method.
            return stub


class _MethodStub:

    def __init__(self, name, input_queue, output_queue):
        self._name = name
        self._input_queue = input_queue
        self._output_queue = output_queue

    def __call__(self, *args, **kwargs):
        self._input_queue.put(_Call(self._name, args, kwargs))
        result, exc = pickle.loads(self._output_queue.get())
        if exc is not None:
            raise exc
        return result


def _process_actor(name, input_queue, output_queue):
    # pylint: disable=too-many-statements

    threading.current_thread().name = name
    logging.basicConfig(
        level=logging.INFO,
        format=(
            '%(asctime)s %(threadName)s %(levelname)s %(name)s: %(message)s'
        ),
    )
    LOG.info('start: pid=%d', os.getpid())

    input_queue._writer.close()
    output_queue._reader.close()
    try:
        self = None
        cls = None

        while True:
            # NOTE:
            #
            # * When handling exceptions, remember to strip off the
            #   stack trace before sending it back (although I think
            #   pickle does this for you?).
            #
            # * Because SimpleQueue.get is blocking, you have to very,
            #   very careful not to block actor's caller indefinitely.
            #   One particular example is pickle.dumps, which fails on
            #   quite many cases, and this is why we call pickle.dumps
            #   explicitly rather than deferring it to SimpleQueue.put.

            try:
                call = input_queue.get()
            except (EOFError, OSError, KeyboardInterrupt) as exc:
                LOG.warning('process actor input queue closed early: %r', exc)
                break

            # Normal exit.
            if call is None:
                break

            # Special method for adopting a new referent.
            if call.method == '__init__':
                self = call.args[0]
                cls = type(self)
                output_queue.put(pickle.dumps((None, None)))
                continue

            # Special method for dis-adopting the referent.
            if call.method == '__del__':
                self = None
                cls = None
                output_queue.put(pickle.dumps((None, None)))
                continue

            if call.method.startswith('_'):
                output_queue.put(
                    pickle.dumps((
                        None,
                        AssertionError(
                            'expect public method: %s' % call.method
                        ),
                    ))
                )
                continue

            if self is None:
                output_queue.put(
                    pickle.dumps((
                        None,
                        AssertionError('expect self not None'),
                    ))
                )
                continue

            cls_method = getattr(cls, call.method, None)
            try:
                method = getattr(self, call.method)
            except AttributeError as exc:
                output_queue.put(
                    pickle.dumps((None, exc.with_traceback(None)))
                )
                continue

            try:
                if cls_method is None or isinstance(cls_method, property):
                    # Instance attribute or property.
                    pair = (method, None)
                elif isinstance(cls_method, types.MethodType):
                    # Class method.
                    pair = (cls_method(*call.args, **call.kwargs), None)
                elif inspect.isgeneratorfunction(cls_method):
                    # Replace generator with a list because generator is
                    # not pickle-able.
                    pair = (list(method(*call.args, **call.kwargs)), None)
                else:
                    # Static method or instance method.
                    pair = (method(*call.args, **call.kwargs), None)
                pair = pickle.dumps(pair)
            except BaseException as exc:
                pair = pickle.dumps((None, exc.with_traceback(None)))
            output_queue.put(pair)
            del pair

    finally:
        input_queue._reader.close()
        output_queue._writer.close()

    LOG.info('exit: pid=%d', os.getpid())
