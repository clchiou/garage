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
import multiprocessing.connection
import multiprocessing.reduction
import os
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
        conn: multiprocessing.connection.Connection = \
            dataclasses.field(compare=False)
        negative_num_uses: int

    def __init__(self, pool_size, max_uses_per_actor=None, context=None):
        # Store processes, sorted by num_uses in descending order.
        self._pool = []
        self._pool_size = pool_size
        # Store id(stub) -> entry.  We store id(stub) to avoid creating
        # a strong reference to the stub.
        self._stub_ids_in_use = {}
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
        for entry in self._stub_ids_in_use.values():
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
        stub = self.get(referent)
        try:
            yield stub
        finally:
            self.return_(stub)

    def get(self, referent):
        """Get a stub from the pool or allocate new one when empty.

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

        try:
            stub = _Stub(type(referent), entry.process, entry.conn)
            stub_id = id(stub)

            # Although this stub_id can be the same as another already
            # collected stub's id (since id is just object's address),
            # it is very unlikely that this id conflict will happen when
            # the entry is still in the self._stub_ids_in_use dict as it
            # requires all these to happen:
            #
            # * The old stub is collected.
            # * The old stub's finalizer has not been called yet (is
            #   this even possible?).
            # * The new stub is allocated, at the same address.
            #
            # But there is not harm to assert this will never happen.
            ASSERT.setitem(self._stub_ids_in_use, stub_id, entry)

            _BoundMethod('_adopt', entry.conn)(referent)
            self._cleanup()

        except Exception:
            if to_spawn:
                self._num_spawns -= 1
                # self._num_concurrent_processes is decreased in
                # self._release.
            self._stub_ids_in_use.pop(stub_id)
            self._release(entry)
            raise

        weakref.finalize(stub, self._return_id, stub_id)
        entry.negative_num_uses -= 1
        self._max_concurrent_processes = max_concurrent_processes
        return stub

    def return_(self, stub):
        """Return the stub to the pool.

        The pool will release actors for actors that exceed the
        ``max_uses_per_actor``, or when the pool is full.
        """
        return self._return_id(id(stub))

    def _return_id(self, stub_id):
        entry = self._stub_ids_in_use.pop(stub_id, None)
        if entry is None:
            return
        try:
            _BoundMethod('_disadopt', entry.conn)()
        except Exception:
            self._release(entry)
            raise
        heapq.heappush(self._pool, entry)
        self._cleanup()

    def _spawn(self):
        conn, conn_actor = self._context.Pipe()
        try:
            name = 'pactor-%02d' % self._COUNTER()
            entry = self._Entry(
                process=self._context.Process(
                    name=name,
                    target=_ProcessActor(name, conn_actor),
                ),
                conn=conn,
                negative_num_uses=0,
            )
            entry.process.start()
            # Block until process actor has received conn_actor; then we
            # may close conn_actor.
            _BoundMethod('_adopt', conn)(None)
        except Exception:
            conn.close()
            raise
        finally:
            conn_actor.close()
        return entry

    def _release(self, entry):
        self._num_concurrent_processes -= 1

        try:
            _conn_send(entry.conn, None)
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
            entry.conn.close()

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
            ASSERT.empty(self._stub_ids_in_use)

        else:
            entries.extend(self._stub_ids_in_use.values())
            self._stub_ids_in_use.clear()
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
                entry.conn.close()


@dataclasses.dataclass(frozen=True)
class _Call:
    method: str
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]


class _Stub:

    def __init__(self, referent_type, process, conn):
        self.m = _Methods(referent_type, process, conn)


class _Methods:

    def __init__(self, referent_type, process, conn):
        self._referent_type = referent_type
        self._process = process
        self._bound_methods = g1_collections.LoadingDict(
            functools.partial(_BoundMethod, conn=conn)
        )

    def __getattr__(self, name):
        ASSERT.none(self._process.exitcode)
        attr = getattr(self._referent_type, name, None)
        bound_method = self._bound_methods[ASSERT.not_startswith(name, '_')]
        if attr is None or isinstance(attr, property):
            # Instance attribute or property.
            return bound_method()
        else:
            # Static/class/instance method.
            return bound_method


class _BoundMethod:

    def __init__(self, name, conn):
        self._name = name
        self._conn = conn

    def __call__(self, *args, **kwargs):
        _conn_send(self._conn, _Call(self._name, args, kwargs))
        result, exc = _conn_recv(self._conn)
        if exc is not None:
            raise exc
        return result


class _ProcessActor:

    # TODO: Get this from g1.apps.loggers?
    _LOG_FORMAT = (
        '%(asctime)s %(threadName)s %(levelname)s %(name)s: %(message)s'
    )

    def __init__(self, name, conn):
        self._name = name
        self._conn = conn
        self._referent = None

    def __call__(self):
        self._process_init()
        try:
            while True:
                try:
                    call = _conn_recv(self._conn)
                except (EOFError, OSError, KeyboardInterrupt) as exc:
                    LOG.warning('actor input closed early: %r', exc)
                    break
                if call is None:  # Normal exit.
                    break
                self._handle(call)
                del call
        except BaseException:
            # Actor only exits due to either self._conn is closed, or
            # call is None.  We treat everything else as crash, even
            # BaseException like SystemExit.
            LOG.exception('actor crashed')
            raise
        finally:
            self._process_cleanup()

    def _process_init(self):
        threading.current_thread().name = self._name
        logging.basicConfig(level=logging.INFO, format=self._LOG_FORMAT)
        LOG.info('start: pid=%d', os.getpid())

    def _process_cleanup(self):
        LOG.info('exit: pid=%d', os.getpid())
        self._conn.close()

    # NOTE:
    #
    # * When handling exceptions, remember to strip off the stack trace
    #   before sending it back (although I think pickle does this for
    #   you?).
    #
    # * Because recv_bytes is blocking, you have to very, very careful
    #   not to block actor's caller indefinitely, waiting for actor's
    #   response.  One particular example is pickle.dumps, which fails
    #   on many cases, and this is why we call ForkingPickler.dumps
    #   explicitly.

    def _handle(self, call):
        # First, check actor methods.
        if call.method == '_adopt':
            self._handle_adopt(call)
        elif call.method == '_disadopt':
            self._handle_disadopt(call)

        # Then, check referent methods.
        elif call.method.startswith('_'):
            self._send_exc(
                AssertionError('expect public method: %s' % call.method)
            )
        elif self._referent is None:
            self._send_exc(AssertionError('expect referent not None'))
        else:
            self._handle_method(call)

    def _send_result(self, result):
        self._conn.send_bytes(self._pickle_pair((result, None)))

    def _send_exc(self, exc):
        self._conn.send_bytes(
            self._pickle_pair((None, exc.with_traceback(None)))
        )

    @staticmethod
    def _pickle_pair(pair):
        try:
            return multiprocessing.reduction.ForkingPickler.dumps(pair)
        except Exception as exc:
            LOG.error('pickle error: pair=%r exc=%r', pair, exc)
            return multiprocessing.reduction.ForkingPickler.dumps(
                (None, exc.with_traceback(None))
            )

    def _handle_adopt(self, call):
        self._referent = call.args[0]
        self._send_result(None)

    def _handle_disadopt(self, call):
        del call  # Unused.
        self._referent = None
        self._send_result(None)

    def _handle_method(self, call):
        try:
            method = getattr(type(self._referent), call.method, None)
            bound_method = getattr(self._referent, call.method)
            if method is None or isinstance(method, property):
                # Instance attribute or property.
                result = bound_method
            elif isinstance(method, types.MethodType):
                # Class method.
                result = method(*call.args, **call.kwargs)
            elif inspect.isgeneratorfunction(bound_method):
                # Replace a generator with a list because generator is
                # not pickle-able.
                result = list(bound_method(*call.args, **call.kwargs))
            else:
                # Static method or instance method.
                result = bound_method(*call.args, **call.kwargs)
        except BaseException as exc:
            self._send_exc(exc)
        else:
            self._send_result(result)


def _conn_send(conn, obj):
    conn.send_bytes(multiprocessing.reduction.ForkingPickler.dumps(obj))


def _conn_recv(conn):
    return multiprocessing.reduction.ForkingPickler.loads(conn.recv_bytes())
