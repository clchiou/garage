__all__ = [
    'DatabaseServer',
]

import collections
import functools
import logging
import time

import sqlalchemy

from g1.asyncs.bases import tasks
from g1.asyncs.bases import timers
from g1.bases.assertions import ASSERT
from g1.operations.databases.bases import interfaces

from . import connections
from . import databases
from . import schemas

# I am not sure why pylint cannot lint contextlib.asynccontextmanager
# correctly; let us disable this check for now.
#
# pylint: disable=not-async-context-manager

LOG = logging.getLogger(__name__)

_TRANSACTION_TIMEOUT = 2  # Unit: seconds.


def _make_reader(database_func):

    @functools.wraps(database_func)
    async def wrapper(self, *, transaction=0, **kwargs):
        if transaction == 0:
            conn_cxt = self._manager.reading()
        else:
            conn_cxt = self._manager.writing(transaction)
        async with conn_cxt as conn:
            return database_func(conn, self._tables, **kwargs)

    return wrapper


def _make_writer(database_func, need_tx_revision=False):

    @functools.wraps(database_func)
    async def wrapper(self, *, transaction=0, **kwargs):
        if transaction == 0:
            conn_cxt = self._manager.transacting()
            if need_tx_revision:
                kwargs['tx_revision'] = None
        else:
            conn_cxt = self._manager.writing(transaction)
            if need_tx_revision:
                kwargs['tx_revision'] = self._tx_revision
            self._update_tx_expiration()
        async with conn_cxt as conn:
            return database_func(conn, self._tables, **kwargs)

    return wrapper


async def _sleep(amount, result):
    await timers.sleep(amount)
    return result


class DatabaseServer(interfaces.DatabaseInterface):

    # DatabaseInterface declares methods as non-async, but we define
    # async methods here; so we have to disable this pylint check for
    # now.
    #
    # pylint: disable=invalid-overridden-method

    def __init__(self, engine, publisher):
        self._engine = engine
        self._manager = connections.ConnectionManager(self._engine.connect())
        self._metadata = sqlalchemy.MetaData()
        self._tables = schemas.make_tables(self._metadata)
        self._tx_revision = None
        # A transaction is automatically rolled back if it is inactive
        # after a certain amount of time.  This is a fail-safe mechanism
        # to prevent deadlocks due to client crashes.
        self._timer_queue = tasks.CompletionQueue()
        self._tx_expiration = time.monotonic()
        # For publishing database events.
        self._publisher = publisher
        self._pending_events = collections.deque()

    async def serve(self):
        await self._check_lease_expiration()
        await self._run_timer_tasks()

    async def _check_lease_expiration(self):
        ASSERT.equal(self._manager.tx_id, 0)
        async with self._manager.reading() as conn:
            expirations = databases.lease_scan_expirations(conn, self._tables)
        now = time.time()
        for expiration in expirations:
            self._timer_queue.spawn(
                _sleep(expiration - now, self._lease_expire)
            )

    async def _run_timer_tasks(self):
        async for timer_task in self._timer_queue:
            timer_callback = timer_task.get_result_nonblocking()
            await timer_callback()

    def shutdown(self):
        for timer_task in self._timer_queue.close(graceful=False):
            timer_task.cancel()

    def __enter__(self):
        LOG.info('database start')
        self._metadata.create_all(self._engine)
        return self

    def __exit__(self, *args):
        LOG.info('database stop')
        self._manager.close()

    #
    # Transactions.
    #

    async def begin(self, *, transaction):
        conn = await self._manager.begin(transaction)
        try:
            self._tx_revision = databases.get_revision(conn, self._tables)
            self._update_tx_expiration()
        except BaseException:
            self._rollback(transaction)
            raise

    async def rollback(self, *, transaction):
        self._rollback(transaction)

    def _rollback(self, transaction):
        self._manager.rollback(transaction)
        self._tx_revision = None
        self._pending_events.clear()

    def _rollback_due_to_timeout(self):
        self._manager.rollback_due_to_timeout()
        self._tx_revision = None
        self._pending_events.clear()

    async def commit(self, *, transaction):
        async with self._manager.writing(transaction) as conn:
            databases.increment_revision(
                conn, self._tables, revision=self._tx_revision
            )
        self._manager.commit(transaction)
        self._tx_revision = None
        try:
            for event in self._pending_events:
                self._publisher.publish_nonblocking(event)
        finally:
            self._pending_events.clear()

    def _update_tx_expiration(self):
        if self._manager.tx_id == 0:
            return
        tx_expiration = time.monotonic() + _TRANSACTION_TIMEOUT
        if tx_expiration > self._tx_expiration:
            self._tx_expiration = tx_expiration
            self._timer_queue.spawn(
                _sleep(_TRANSACTION_TIMEOUT, self._check_tx_expiration)
            )

    # Make the signature of this function async to keep it the same with
    # _lease_expire.
    async def _check_tx_expiration(self):
        if self._manager.tx_id == 0:
            return
        if self._tx_expiration >= time.monotonic():
            return
        LOG.warning('transaction timeout: %#016x', self._manager.tx_id)
        self._rollback_due_to_timeout()

    #
    # Key-value operations.
    #

    get_revision = _make_reader(databases.get_revision)
    get = _make_reader(databases.get)
    count = _make_reader(databases.count)
    scan_keys = _make_reader(databases.scan_keys)
    scan = _make_reader(databases.scan)
    _set = _make_writer(databases.set_, need_tx_revision=True)
    _delete = _make_writer(databases.delete, need_tx_revision=True)

    async def set(self, *, key, value, transaction=0):
        prior = await self._set(key=key, value=value, transaction=transaction)
        if prior is None or prior.value != value:
            if transaction != 0:
                revision = ASSERT.not_none(self._tx_revision) + 1
            else:
                ASSERT.equal(self._manager.tx_id, 0)
                async with self._manager.reading() as conn:
                    revision = databases.get_revision(conn, self._tables)
            self._maybe_publish_events(
                transaction,
                [
                    interfaces.DatabaseEvent(
                        previous=prior,
                        current=interfaces.KeyValue(
                            revision=revision, key=key, value=value
                        ),
                    ),
                ],
            )
        return prior

    async def delete(self, *, key_start=b'', key_end=b'', transaction=0):
        prior = await self._delete(
            key_start=key_start, key_end=key_end, transaction=transaction
        )
        self._maybe_publish_events(
            transaction,
            (
                interfaces.DatabaseEvent(previous=previous, current=None)
                for previous in prior
            ),
        )
        return prior

    def _maybe_publish_events(self, transaction, events):
        if transaction == 0:
            for event in events:
                self._publisher.publish_nonblocking(event)
        else:
            self._pending_events.extend(events)

    #
    # Leases.
    #

    lease_get = _make_reader(databases.lease_get)
    lease_count = _make_reader(databases.lease_count)
    lease_scan = _make_reader(databases.lease_scan)
    _lease_grant = _make_writer(databases.lease_grant)
    lease_associate = _make_writer(databases.lease_associate)
    lease_dissociate = _make_writer(databases.lease_dissociate)
    lease_revoke = _make_writer(databases.lease_revoke)

    async def lease_grant(self, **kwargs):  # pylint: disable=arguments-differ
        result = await self._lease_grant(**kwargs)
        self._timer_queue.spawn(
            _sleep(kwargs['expiration'] - time.time(), self._lease_expire)
        )
        return result

    async def _lease_expire(self):
        prior = ()
        try:
            async with self._manager.transacting() as conn:
                prior = databases.lease_expire(
                    conn, self._tables, current_time=time.time()
                )
        except interfaces.TransactionTimeoutError:
            LOG.warning('lease_expire: timeout on beginning transaction')
        if prior:
            LOG.info('expire %d pairs', len(prior))
            self._maybe_publish_events(
                0,
                (
                    interfaces.DatabaseEvent(previous=previous, current=None)
                    for previous in prior
                ),
            )

    #
    # Maintenance.
    #

    async def compact(self, **kwargs):  # pylint: disable=arguments-differ
        async with self._manager.transacting() as conn:
            return databases.compact(conn, self._tables, **kwargs)
