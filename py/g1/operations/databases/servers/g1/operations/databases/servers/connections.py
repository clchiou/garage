__all__ = [
    'ConnectionManager',
]

import collections
import contextlib
import logging

from g1.asyncs.bases import locks
from g1.asyncs.bases import timers
from g1.bases import assertions
from g1.bases.assertions import ASSERT
from g1.operations.databases.bases import interfaces

LOG = logging.getLogger(__name__)

ASSERT_REQUEST = assertions.Assertions(
    lambda *_: interfaces.InvalidRequestError()
)

_WAIT_FOR_READER = 2  # Unit: seconds.
_WAIT_FOR_WRITER = 2  # Unit: seconds.

_NUM_REMEMBERED = 8


class ConnectionManager:
    """Connection manager.

    This protects concurrent access to the underlying connection object
    by providing a reader-writer lock interface guarding the connection
    object.  This mimics SQLite's transaction model that is also a
    reader-writer lock (I am not sure if this is a good idea).
    """

    def __init__(self, conn):
        self._conn = conn
        # To implement reader lock.
        self._num_readers = 0
        self._num_readers_gate = locks.Gate()
        # To implement writer lock.
        self._tx_id = 0
        self._tx_id_gate = locks.Gate()
        self._tx = None
        # Use collections.deque as a bounded list to track completed
        # transaction completion states.  They are a best effort for
        # generating user-friendly error responses.
        self._rollback_tx_ids = collections.deque(maxlen=_NUM_REMEMBERED)
        self._commit_tx_ids = collections.deque(maxlen=_NUM_REMEMBERED)
        self._timeout_tx_ids = collections.deque(maxlen=_NUM_REMEMBERED)

    @property
    def tx_id(self):
        return self._tx_id

    def close(self):
        if self._tx_id != 0:
            LOG.warning('roll back transaction on close: %#016x', self._tx_id)
            self.rollback_due_to_timeout()
        self._conn.close()
        self._conn = None  # Make sure this manager becomes unusable.

    #
    # Reader-writer lock.
    #

    @contextlib.asynccontextmanager
    async def reading(self):
        """Use connection in a read transaction."""
        await self._wait_for_writer()
        self._num_readers += 1
        try:
            yield self._conn
        finally:
            self._num_readers -= 1
            if self._num_readers == 0:
                self._num_readers_gate.unblock()

    @contextlib.asynccontextmanager
    async def writing(self, tx_id):
        """Use connection in a write transaction."""
        ASSERT_REQUEST.greater(tx_id, 0)
        if tx_id != self._tx_id:
            if tx_id in self._timeout_tx_ids:
                raise interfaces.TransactionTimeoutError
            raise interfaces.TransactionNotFoundError
        yield self._conn

    @contextlib.asynccontextmanager
    async def transacting(self):
        """Use connection in a one-shot write transaction."""
        tx_id = interfaces.generate_transaction_id()
        await self.begin(tx_id)
        try:
            yield self._conn
        except BaseException:
            self.rollback(tx_id)
            raise
        else:
            self.commit(tx_id)

    async def _wait_for_reader(self):
        if self._num_readers == 0:
            return
        with timers.timeout_ignore(_WAIT_FOR_READER):
            while self._num_readers != 0:
                await self._num_readers_gate.wait()
        if self._num_readers != 0:
            LOG.warning('wait for reader timeout: %d', self._num_readers)
            raise interfaces.TransactionTimeoutError

    async def _wait_for_writer(self):
        if self._tx_id == 0:
            return
        with timers.timeout_ignore(_WAIT_FOR_WRITER):
            while self._tx_id != 0:
                await self._tx_id_gate.wait()
        if self._tx_id != 0:
            LOG.warning('wait for writer timeout: %#016x', self._tx_id)
            raise interfaces.TransactionTimeoutError

    #
    # "begin" transactions.
    #

    async def begin(self, tx_id):
        ASSERT_REQUEST.greater(tx_id, 0)
        if tx_id == self._tx_id:
            return self._conn  # begin is idempotent.
        await self._wait_for_reader()
        await self._wait_for_writer()
        # It is possible that _wait_for_writer is about to return but
        # this task is not scheduled to execute, and another reader
        # takes place first; so let's check _num_readers again.
        if self._num_readers != 0:
            LOG.warning('another reader preempt the begin: %#016x', tx_id)
            raise interfaces.TransactionTimeoutError
        LOG.info('begin transaction: %#016x', tx_id)
        self._tx_id = tx_id
        self._tx = self._conn.begin()
        return self._conn

    #
    # "end" transactions.
    #

    def rollback(self, tx_id):
        if not self._check_end(
            tx_id, self._rollback_tx_ids, self._timeout_tx_ids
        ):
            return
        self._tx.rollback()
        self._end(self._rollback_tx_ids)

    def rollback_due_to_timeout(self):
        ASSERT.not_equal(self._tx_id, 0)
        self._tx.rollback()
        self._end(self._timeout_tx_ids)

    def commit(self, tx_id):
        if not self._check_end(tx_id, self._commit_tx_ids):
            return
        self._tx.commit()
        self._end(self._commit_tx_ids)

    def _check_end(self, tx_id, *tx_id_lists):
        """Check preconditions of an "end" call."""
        ASSERT_REQUEST.greater(tx_id, 0)
        # Do not check self._tx_id == 0 to support idempotent end.
        if tx_id == self._tx_id:
            return True
        elif any(tx_id in tx_id_list for tx_id_list in tx_id_lists):
            return False  # end is idempotent.
        else:
            raise interfaces.TransactionNotFoundError

    def _end(self, tx_id_lists):
        LOG.info('end transaction: %#016x', self._tx_id)
        tx_id_lists.append(self._tx_id)
        self._tx_id = 0
        self._tx = None
        self._tx_id_gate.unblock()
