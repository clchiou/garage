import unittest
import unittest.mock

import functools

from g1.asyncs import kernels
from g1.operations.databases.bases import interfaces
from g1.operations.databases.servers import connections

# I am not sure why pylint cannot lint contextlib.asynccontextmanager
# correctly; let us disable this check for now.
#
# pylint: disable=not-async-context-manager


def synchronous(test_method):

    @kernels.with_kernel
    @functools.wraps(test_method)
    def wrapper(self):
        kernels.run(test_method(self))

    return wrapper


class ConnectionsTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.conn = unittest.mock.Mock()
        self.tx = self.conn.begin.return_value
        self.manager = connections.ConnectionManager(self.conn)
        unittest.mock.patch.multiple(
            connections,
            _WAIT_FOR_READER=0.01,
            _WAIT_FOR_WRITER=0.01,
        ).start()

    def tearDown(self):
        unittest.mock.patch.stopall()
        super().tearDown()

    def assert_manager(
        self,
        num_readers,
        tx_id,
        rollback_tx_ids,
        commit_tx_ids,
        timeout_tx_ids,
    ):
        self.assertEqual(self.manager._num_readers, num_readers)
        self.assertEqual(self.manager._tx_id, tx_id)
        self.assertEqual(tuple(self.manager._rollback_tx_ids), rollback_tx_ids)
        self.assertEqual(tuple(self.manager._commit_tx_ids), commit_tx_ids)
        self.assertEqual(tuple(self.manager._timeout_tx_ids), timeout_tx_ids)
        self.assertEqual(self.manager.tx_id, tx_id)

    @synchronous
    async def test_reading(self):
        self.assert_manager(0, 0, (), (), ())
        async with self.manager.reading() as conn_1:
            self.assert_manager(1, 0, (), (), ())
            self.assertIs(conn_1, self.conn)
            async with self.manager.reading() as conn_2:
                self.assert_manager(2, 0, (), (), ())
                self.assertIs(conn_2, self.conn)
                async with self.manager.reading() as conn_3:
                    self.assert_manager(3, 0, (), (), ())
                    self.assertIs(conn_3, self.conn)
                self.assert_manager(2, 0, (), (), ())
            self.assert_manager(1, 0, (), (), ())
        self.assert_manager(0, 0, (), (), ())
        self.conn.begin.assert_not_called()

    @synchronous
    async def test_reading_timeout(self):
        self.assert_manager(0, 0, (), (), ())
        async with self.manager.transacting():
            tx_id = self.manager.tx_id
            with self.assertRaises(interfaces.TransactionTimeoutError):
                async with self.manager.reading():
                    pass
        self.assert_manager(0, 0, (), (tx_id, ), ())
        self.conn.begin.assert_called_once()

    @synchronous
    async def test_writing(self):
        with self.assertRaises(interfaces.InvalidRequestError):
            async with self.manager.writing(0):
                pass
        with self.assertRaises(interfaces.TransactionNotFoundError):
            async with self.manager.writing(1):
                pass
        self.assert_manager(0, 0, (), (), ())
        async with self.manager.transacting():
            tx_id = self.manager.tx_id
            self.assert_manager(0, tx_id, (), (), ())
            async with self.manager.writing(tx_id) as conn:
                self.assert_manager(0, tx_id, (), (), ())
                self.assertIs(conn, self.conn)
            with self.assertRaises(interfaces.TransactionNotFoundError):
                async with self.manager.writing(tx_id + 1):
                    pass
        self.assert_manager(0, 0, (), (tx_id, ), ())
        self.conn.begin.assert_called_once()

    @synchronous
    async def test_transacting(self):
        self.assert_manager(0, 0, (), (), ())
        async with self.manager.transacting() as conn:
            tx_id = self.manager.tx_id
            self.assertNotEqual(tx_id, 0)
            self.assert_manager(0, tx_id, (), (), ())
            self.assertIs(conn, self.conn)
        self.assert_manager(0, 0, (), (tx_id, ), ())
        self.conn.begin.assert_called_once()

    @synchronous
    async def test_transacting_rollback(self):
        self.assert_manager(0, 0, (), (), ())
        with self.assertRaises(ValueError):
            async with self.manager.transacting():
                tx_id = self.manager.tx_id
                raise ValueError
        self.assert_manager(0, 0, (tx_id, ), (), ())
        self.conn.begin.assert_called_once()

    @synchronous
    async def test_transacting_timeout_on_reader(self):
        self.assert_manager(0, 0, (), (), ())
        async with self.manager.reading():
            with self.assertRaises(interfaces.TransactionTimeoutError):
                async with self.manager.transacting():
                    pass
        self.assert_manager(0, 0, (), (), ())
        self.conn.begin.assert_not_called()

    @synchronous
    async def test_transacting_timeout_on_writer(self):
        self.assert_manager(0, 0, (), (), ())
        async with self.manager.transacting():
            tx_id = self.manager.tx_id
            with self.assertRaises(interfaces.TransactionTimeoutError):
                async with self.manager.transacting():
                    pass
        self.assert_manager(0, 0, (), (tx_id, ), ())
        self.conn.begin.assert_called_once()

    @synchronous
    async def test_begin(self):
        with self.assertRaises(interfaces.InvalidRequestError):
            await self.manager.begin(0)
        self.assert_manager(0, 0, (), (), ())
        conn = await self.manager.begin(1)
        for _ in range(3):  # begin is idempotent.
            self.assertIs(await self.manager.begin(1), conn)
        self.assertIs(conn, self.conn)
        self.assert_manager(0, 1, (), (), ())
        with self.assertRaises(interfaces.TransactionTimeoutError):
            await self.manager.begin(2)
        self.conn.begin.assert_called_once()

    @synchronous
    async def test_end(self):
        with self.assertRaises(interfaces.InvalidRequestError):
            await self.manager.rollback(0)
        with self.assertRaises(interfaces.InvalidRequestError):
            await self.manager.commit(0)

        with self.assertRaises(interfaces.TransactionNotFoundError):
            await self.manager.rollback(1)
        with self.assertRaisesRegex(AssertionError, r'expect x != 0'):
            await self.manager.rollback_due_to_timeout()
        with self.assertRaises(interfaces.TransactionNotFoundError):
            await self.manager.commit(1)

        self.assert_manager(0, 0, (), (), ())
        await self.manager.begin(1)
        self.assert_manager(0, 1, (), (), ())
        with self.assertRaises(interfaces.TransactionNotFoundError):
            self.manager.rollback(999)
        with self.assertRaises(interfaces.TransactionNotFoundError):
            self.manager.commit(999)

        self.tx.rollback.assert_not_called()
        for _ in range(3):  # rollback is idempotent.
            self.manager.rollback(1)
        self.tx.rollback.assert_called_once()
        self.assert_manager(0, 0, (1, ), (), ())

        await self.manager.begin(2)
        self.tx.commit.assert_not_called()
        for _ in range(3):  # commit is idempotent.
            self.manager.commit(2)
        self.tx.commit.assert_called_once()
        self.assert_manager(0, 0, (1, ), (2, ), ())

        self.tx.rollback.reset_mock()
        await self.manager.begin(3)
        self.manager.rollback_due_to_timeout()
        self.tx.rollback.assert_called_once()
        self.assert_manager(0, 0, (1, ), (2, ), (3, ))

        await self.manager.begin(1)
        with self.assertRaises(interfaces.TransactionTimeoutError):
            async with self.manager.writing(3):
                pass
        with self.assertRaises(interfaces.TransactionNotFoundError):
            async with self.manager.writing(4):
                pass


if __name__ == '__main__':
    unittest.main()
