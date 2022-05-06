import unittest
import unittest.mock

import functools

from g1.asyncs import kernels
from g1.asyncs.bases import tasks
from g1.databases import sqlite
from g1.operations.databases.bases import interfaces
from g1.operations.databases.servers import connections
from g1.operations.databases.servers import servers


def synchronous(test_method):

    @kernels.with_kernel
    @functools.wraps(test_method)
    def wrapper(self):
        with self.server:
            kernels.run(test_method(self))
            self.server.shutdown()

    return wrapper


def with_kernel(test_method):

    @kernels.with_kernel
    @functools.wraps(test_method)
    def wrapper(self):
        with self.server:
            test_method(self)
            self.server.shutdown()

    return wrapper


def de(p, c):
    return interfaces.DatabaseEvent(previous=p, current=c)


def kv(r, k, v):
    return interfaces.KeyValue(revision=r, key=k, value=v)


class ServersTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        unittest.mock.patch.multiple(
            connections,
            _WAIT_FOR_READER=0.01,
            _WAIT_FOR_WRITER=0.01,
        ).start()
        unittest.mock.patch.multiple(
            servers,
            _TRANSACTION_TIMEOUT=0.01,
        ).start()
        mock_time = unittest.mock.patch(servers.__name__ + '.time').start()
        self.mock_monotonic = mock_time.monotonic
        self.mock_monotonic.return_value = 0
        self.mock_time = mock_time.time
        self.mock_time.return_value = 0
        self.engine = sqlite.create_engine('sqlite://')
        self.publisher = unittest.mock.Mock()
        self.server = servers.DatabaseServer(self.engine, self.publisher)

    def tearDown(self):
        unittest.mock.patch.stopall()
        super().tearDown()

    def assert_publish(self, events):
        if not events:
            self.publisher.publish_nonblocking.assert_not_called()
        else:
            self.publisher.publish_nonblocking.assert_has_calls([
                unittest.mock.call(event) for event in events
            ])

    @synchronous
    async def test_no_transaction(self):
        self.assertEqual(await self.server.get_revision(), 0)
        self.assertIsNone(await self.server.get(key=b'k1'))
        self.assert_publish([])

        self.assertIsNone(await self.server.set(key=b'k1', value=b'v1'))
        self.assertEqual(await self.server.get_revision(), 1)
        self.assertEqual(
            await self.server.get(key=b'k1'),
            interfaces.KeyValue(revision=1, key=b'k1', value=b'v1'),
        )
        self.assert_publish([de(None, kv(1, b'k1', b'v1'))])

        self.assertEqual(
            await self.server.set(key=b'k1', value=b'v2'),
            interfaces.KeyValue(revision=1, key=b'k1', value=b'v1'),
        )
        self.assertEqual(await self.server.get_revision(), 2)
        self.assertEqual(
            await self.server.get(key=b'k1'),
            interfaces.KeyValue(revision=2, key=b'k1', value=b'v2'),
        )
        self.assert_publish([
            de(None, kv(1, b'k1', b'v1')),
            de(kv(1, b'k1', b'v1'), kv(2, b'k1', b'v2')),
        ])

        self.assertEqual(
            await self.server.delete(),
            [interfaces.KeyValue(revision=2, key=b'k1', value=b'v2')],
        )
        self.assertEqual(await self.server.get_revision(), 3)
        self.assertIsNone(await self.server.get(key=b'k1'))
        self.assert_publish([
            de(None, kv(1, b'k1', b'v1')),
            de(kv(1, b'k1', b'v1'), kv(2, b'k1', b'v2')),
            de(kv(2, b'k1', b'v2'), None),
        ])

    @synchronous
    async def test_transaction(self):
        await self.server.begin(transaction=1)
        self.assertEqual(await self.server.get_revision(transaction=1), 0)
        self.assertEqual(self.server._tx_revision, 0)
        self.assertIsNone(await self.server.get(key=b'k1', transaction=1))
        self.assertIsNone(
            await self.server.set(key=b'k1', value=b'v1', transaction=1)
        )
        # In a transaction, revision is incremented at the end.
        self.assertEqual(await self.server.get_revision(transaction=1), 0)
        self.assertEqual(
            await self.server.get(key=b'k1', transaction=1),
            interfaces.KeyValue(revision=1, key=b'k1', value=b'v1'),
        )
        self.assert_publish([])
        await self.server.commit(transaction=1)
        self.assert_publish([de(None, kv(1, b'k1', b'v1'))])

        self.assertEqual(await self.server.get_revision(), 1)
        self.assertEqual(
            await self.server.get(key=b'k1'),
            interfaces.KeyValue(revision=1, key=b'k1', value=b'v1'),
        )

        self.publisher.publish_nonblocking.reset_mock()
        await self.server.begin(transaction=2)
        self.assertEqual(await self.server.get_revision(transaction=2), 1)
        self.assertEqual(self.server._tx_revision, 1)
        self.assertEqual(
            await self.server.set(key=b'k1', value=b'v2', transaction=2),
            interfaces.KeyValue(revision=1, key=b'k1', value=b'v1'),
        )
        # In a transaction, revision is incremented at the end.
        self.assertEqual(await self.server.get_revision(transaction=2), 1)
        self.assertEqual(
            await self.server.get(key=b'k1', transaction=2),
            interfaces.KeyValue(revision=2, key=b'k1', value=b'v2'),
        )
        await self.server.rollback(transaction=2)
        self.publisher.publish_nonblocking.assert_not_called()

        self.assertEqual(await self.server.get_revision(), 1)
        self.assertEqual(
            await self.server.get(key=b'k1'),
            interfaces.KeyValue(revision=1, key=b'k1', value=b'v1'),
        )

    @with_kernel
    def test_transaction_expired(self):
        self.assertEqual(tuple(self.server._manager._timeout_tx_ids), ())
        kernels.run(self.server.begin(transaction=1))
        self.assertEqual(self.server._manager.tx_id, 1)
        self.mock_monotonic.return_value = 10
        server_task = tasks.spawn(self.server._run_timer_tasks)
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.02)
        self.assertEqual(self.server._manager.tx_id, 0)
        self.assertEqual(tuple(self.server._manager._timeout_tx_ids), (1, ))

        self.server.shutdown()
        kernels.run(timeout=0.01)
        self.assertIsNone(server_task.get_result_nonblocking())

    @with_kernel
    def test_lease_expired(self):
        kernels.run(self.server.set(key=b'k1', value=b'v1'))
        kernels.run(self.server.lease_grant(lease=1, expiration=0.01))
        kernels.run(self.server.lease_associate(lease=1, key=b'k1'))
        self.assertEqual(kernels.run(self.server.get_revision()), 1)
        self.assertEqual(
            kernels.run(self.server.get(key=b'k1')),
            interfaces.KeyValue(revision=1, key=b'k1', value=b'v1'),
        )
        self.assertEqual(
            kernels.run(self.server.lease_get(lease=1)),
            interfaces.Lease(lease=1, expiration=0.01, keys=(b'k1', )),
        )

        server_task = tasks.spawn(self.server._run_timer_tasks)
        self.mock_time.return_value = 10
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.02)
        self.assertEqual(kernels.run(self.server.get_revision()), 2)
        self.assertIsNone(kernels.run(self.server.get(key=b'k1')))
        self.assertIsNone(kernels.run(self.server.lease_get(lease=1)))
        self.assert_publish([de(None, kv(1, b'k1', b'v1'))])

        self.server.shutdown()
        kernels.run(timeout=0.01)
        self.assertIsNone(server_task.get_result_nonblocking())

    @synchronous
    async def test_set_not_publish(self):
        self.assertIsNone(await self.server.set(key=b'k1', value=b'v1'))
        self.publisher.publish_nonblocking.assert_called_once_with(
            interfaces.DatabaseEvent(
                previous=None,
                current=kv(1, b'k1', b'v1'),
            ),
        )
        self.publisher.publish_nonblocking.reset_mock()

        self.assertEqual(
            await self.server.set(key=b'k1', value=b'v1'),
            kv(1, b'k1', b'v1'),
        )
        self.publisher.publish_nonblocking.assert_not_called()


if __name__ == '__main__':
    unittest.main()
