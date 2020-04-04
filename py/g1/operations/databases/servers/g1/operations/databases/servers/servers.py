__all__ = [
    'DatabaseServer',
]

import functools
import logging
import time

import sqlalchemy

from g1.asyncs.bases import tasks
from g1.asyncs.bases import timers
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

    def __init__(self, engine):
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

    async def serve(self):
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

    def _rollback_due_to_timeout(self):
        self._manager.rollback_due_to_timeout()
        self._tx_revision = None

    async def commit(self, *, transaction):
        async with self._manager.writing(transaction) as conn:
            databases.increment_revision(
                conn, self._tables, revision=self._tx_revision
            )
        self._manager.commit(transaction)
        self._tx_revision = None

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
    set = _make_writer(databases.set, need_tx_revision=True)
    delete = _make_writer(databases.delete, need_tx_revision=True)

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
        try:
            async with self._manager.transacting() as conn:
                keys = databases.lease_expire(
                    conn, self._tables, current_time=time.time()
                )
                if keys:
                    LOG.info('expire keys: %r', keys)
        except interfaces.TransactionTimeoutError:
            LOG.warning('lease_expire: timeout on beginning transaction')

    #
    # Maintenance.
    #

    async def compact(self, **kwargs):  # pylint: disable=arguments-differ
        async with self._manager.transacting() as conn:
            return databases.compact(conn, self._tables, **kwargs)
