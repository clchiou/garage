import unittest
import unittest.mock

import heapq
import itertools
import logging
import multiprocessing
import multiprocessing.connection
import os
import pickle
import tempfile

from g1.bases import pools


def setUpModule():
    # Disable all log messages (for _ProcessActor).
    logging.basicConfig(level=logging.CRITICAL + 1)


class TimeoutPoolTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.mock_allocate = unittest.mock.Mock()
        self.mock_allocate.side_effect = itertools.count()
        self.mock_release = unittest.mock.Mock()
        self.pool = pools.TimeoutPool(4, self.mock_allocate, self.mock_release)

    def assert_pool(
        self,
        expect_pool,
        expect_num_allocations,
        expect_num_concurrent_resources,
        expect_max_concurrent_resources,
    ):
        self.assertEqual(list(self.pool._pool), expect_pool)
        stats = self.pool.get_stats()
        self.assertEqual(stats.num_allocations, expect_num_allocations)
        self.assertEqual(
            stats.num_concurrent_resources, expect_num_concurrent_resources
        )
        self.assertEqual(
            stats.max_concurrent_resources, expect_max_concurrent_resources
        )

    @unittest.mock.patch.object(pools, 'time')
    def test_pool_not_timed(self, mock_time):
        mock_time.monotonic.return_value = 1001

        self.assert_pool([], 0, 0, 0)
        for i in range(5):
            self.assertEqual(self.pool.get(), i)
            self.assert_pool([], i + 1, i + 1, i + 1)

        for i in reversed(range(1, 5)):
            self.pool.return_(i)
            self.assert_pool(
                [(j, 1001) for j in reversed(range(i, 5))],
                5,
                5,
                5,
            )
        self.pool.return_(0)
        self.assert_pool([(j, 1001) for j in reversed(range(4))], 5, 4, 5)

        self.pool.cleanup()
        self.assert_pool([(j, 1001) for j in reversed(range(4))], 5, 4, 5)

        self.pool.close()
        self.assert_pool([], 5, 0, 5)

        for i in range(5, 10):
            self.assertEqual(self.pool.get(), i)
            self.assert_pool([], i + 1, i - 4, 5)
        self.assertEqual(self.pool.get(), 10)
        self.assert_pool([], 11, 6, 6)

        self.assertEqual(len(self.mock_allocate.mock_calls), 11)
        self.mock_release.assert_has_calls([
            unittest.mock.call(i) for i in reversed(range(5))
        ])

    @unittest.mock.patch.object(pools, 'time')
    def test_timeout(self, mock_time):
        mock_monotonic = mock_time.monotonic
        self.assert_pool([], 0, 0, 0)

        for i in range(4):
            self.assertEqual(self.pool.get(), i)
        self.assert_pool([], 4, 4, 4)

        mock_monotonic.return_value = 1000
        self.pool.return_(0)
        self.assert_pool([(0, 1000)], 4, 4, 4)

        mock_monotonic.return_value = 1100
        self.pool.return_(1)
        self.assert_pool([(0, 1000), (1, 1100)], 4, 4, 4)

        mock_monotonic.return_value = 1200
        self.pool.return_(2)
        self.assert_pool([(0, 1000), (1, 1100), (2, 1200)], 4, 4, 4)

        mock_monotonic.return_value = 1300
        self.pool.return_(3)
        self.assert_pool([(0, 1000), (1, 1100), (2, 1200), (3, 1300)], 4, 4, 4)

        self.assertEqual(self.pool.get(), 3)
        self.assert_pool([(0, 1000), (1, 1100), (2, 1200)], 4, 4, 4)
        self.pool.return_(3)
        self.assert_pool([(0, 1000), (1, 1100), (2, 1200), (3, 1300)], 4, 4, 4)

        # Test `get` returning the most recently returned resource.
        mock_monotonic.return_value = 1400
        self.assertEqual(self.pool.get(), 3)
        self.assert_pool([(1, 1100), (2, 1200)], 4, 3, 4)

        mock_monotonic.return_value = 1500
        self.pool.return_(3)
        self.assert_pool([(2, 1200), (3, 1500)], 4, 2, 4)

        mock_monotonic.return_value = 1600
        self.pool.cleanup()
        self.assert_pool([(3, 1500)], 4, 1, 4)

        self.assertEqual(len(self.mock_allocate.mock_calls), 4)
        self.mock_release.assert_has_calls([
            unittest.mock.call(0),
            unittest.mock.call(1),
            unittest.mock.call(2),
        ])

    @unittest.mock.patch.object(pools, 'time')
    def test_context(self, mock_time):
        mock_time.monotonic.return_value = 1001

        self.assert_pool([], 0, 0, 0)
        with self.pool:
            for i in range(4):
                self.assertEqual(self.pool.get(), i)
                self.assert_pool([], i + 1, i + 1, i + 1)
            for i in reversed(range(4)):
                self.pool.return_(i)
                self.assert_pool(
                    [(j, 1001) for j in reversed(range(i, 4))],
                    4,
                    4,
                    4,
                )
        self.assert_pool([], 4, 0, 4)

        self.assertEqual(len(self.mock_allocate.mock_calls), 4)
        self.mock_release.assert_has_calls([
            unittest.mock.call(i) for i in reversed(range(4))
        ])

    @unittest.mock.patch.object(pools, 'time')
    def test_using(self, mock_time):
        mock_time.monotonic.return_value = 1001

        self.assert_pool([], 0, 0, 0)
        with self.pool.using() as r0:
            self.assertEqual(r0, 0)
            self.assert_pool([], 1, 1, 1)
            with self.pool.using() as r1:
                self.assertEqual(r1, 1)
                self.assert_pool([], 2, 2, 2)
            self.assert_pool([(1, 1001)], 2, 2, 2)
        self.assert_pool([(1, 1001), (0, 1001)], 2, 2, 2)

        # Test `get` returning the most recently returned resource.
        for _ in range(3):
            with self.pool.using() as r0:
                self.assertEqual(r0, 0)
                self.assert_pool([(1, 1001)], 2, 2, 2)
        self.assert_pool([(1, 1001), (0, 1001)], 2, 2, 2)

        self.assertEqual(len(self.mock_allocate.mock_calls), 2)
        self.mock_release.assert_not_called()


class ProcessActorPoolTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.mock_context = unittest.mock.Mock()
        self.pool = pools.ProcessActorPool(4, 1, self.mock_context)

    def assert_pool(
        self,
        expect_pool,
        expect_stub_ids_in_use,
        expect_num_spawns,
        expect_num_concurrent_processes,
        expect_max_concurrent_processes,
    ):
        expect_pool = list(expect_pool)
        heapq.heapify(expect_pool)
        self.assertEqual(self.pool._pool, expect_pool)
        self.assertEqual(self.pool._stub_ids_in_use, expect_stub_ids_in_use)
        stats = self.pool.get_stats()
        self.assertEqual(stats.num_spawns, expect_num_spawns)
        self.assertEqual(
            stats.num_concurrent_processes, expect_num_concurrent_processes
        )
        self.assertEqual(
            stats.max_concurrent_processes, expect_max_concurrent_processes
        )
        self.assertEqual(
            stats.current_highest_uses,
            max(
                map(
                    lambda entry: -entry.negative_num_uses,
                    itertools.chain(
                        expect_pool,
                        expect_stub_ids_in_use.values(),
                    ),
                ),
                default=0,
            ),
        )

    @staticmethod
    def assert_process(mock_process, progress):
        if progress < 1:
            mock_process.start.assert_not_called()
        else:
            mock_process.start.assert_called_once_with()
        if progress < 2:
            mock_process.join.assert_not_called()
        else:
            mock_process.join.assert_called_once_with(timeout=1)
        if progress < 3:
            mock_process.close.assert_not_called()
        else:
            mock_process.close.assert_called_once_with()

    def assert_conn(self, mock_conn, *calls):
        mock_conn.send_bytes.assert_has_calls([
            unittest.mock.call(pickle.dumps(call)) for call in calls
        ])
        self.assertEqual(
            len(mock_conn.recv_bytes.mock_calls),
            sum(1 for call in calls if call is not None),
        )
        if calls and calls[-1] is None:
            mock_conn.close.assert_called_once_with()
        else:
            mock_conn.close.assert_not_called()

    def test_get_and_return(self):
        mock_exitcode = unittest.mock.PropertyMock()
        mock_process = self.mock_context.Process.return_value
        mock_process.pid = 1
        type(mock_process).exitcode = mock_exitcode
        mock_conn = unittest.mock.Mock()
        mock_conn.recv_bytes.return_value = pickle.dumps((None, None))
        mock_actor_conn = unittest.mock.Mock()
        self.mock_context.Pipe.return_value = (mock_conn, mock_actor_conn)
        referent = object()

        self.assert_pool([], {}, 0, 0, 0)

        mock_exitcode.return_value = None

        a1 = self.pool.get(referent)
        e1 = pools.ProcessActorPool._Entry(
            process=mock_process,
            conn=mock_conn,
            negative_num_uses=-1,
        )
        self.assert_pool([], {id(a1): e1}, 1, 1, 1)
        self.assert_process(mock_process, 1)
        self.assert_conn(
            mock_conn,
            pools._Call('_adopt', (None, ), {}),
            pools._Call('_adopt', (referent, ), {}),
        )
        mock_actor_conn.close.assert_called_once_with()

        for _ in range(3):  # Returning a returned stub is no-op.
            self.pool.return_(a1)
        self.assert_pool([e1], {}, 1, 1, 1)
        self.assert_process(mock_process, 1)
        self.assert_conn(
            mock_conn,
            pools._Call('_adopt', (None, ), {}),
            pools._Call('_adopt', (referent, ), {}),
            pools._Call('_disadopt', (), {}),
        )

        mock_exitcode.return_value = 0

        with self.pool.using(referent) as a2:
            e1.negative_num_uses = -2
            self.assert_pool([], {id(a2): e1}, 1, 1, 1)
            self.assert_process(mock_process, 1)
            self.assert_conn(
                mock_conn,
                pools._Call('_adopt', (None, ), {}),
                pools._Call('_adopt', (referent, ), {}),
                pools._Call('_disadopt', (), {}),
                pools._Call('_adopt', (referent, ), {}),
            )

        self.assert_pool([], {}, 1, 0, 1)
        self.assert_process(mock_process, 3)
        self.assert_conn(
            mock_conn,
            pools._Call('_adopt', (None, ), {}),
            pools._Call('_adopt', (referent, ), {}),
            pools._Call('_disadopt', (), {}),
            pools._Call('_adopt', (referent, ), {}),
            pools._Call('_disadopt', (), {}),
            None,
        )

    def test_heap(self):
        mock_process = self.mock_context.Process.return_value
        mock_process.pid = 1
        mock_process.exitcode = None
        mock_conn = unittest.mock.Mock()
        mock_actor_conn = unittest.mock.Mock()
        self.mock_context.Pipe.return_value = (mock_conn, mock_actor_conn)
        mock_conn.recv_bytes.return_value = pickle.dumps((None, None))
        referent = object()

        self.pool._max_uses_per_actor = None

        a0 = self.pool.get(referent)
        a1 = self.pool.get(referent)
        e0 = pools.ProcessActorPool._Entry(
            process=mock_process,
            conn=mock_conn,
            negative_num_uses=-1,
        )
        e1 = pools.ProcessActorPool._Entry(
            process=mock_process,
            conn=mock_conn,
            negative_num_uses=-1,
        )
        self.pool.return_(a0)
        self.pool.return_(a1)
        self.assert_pool([e0, e1], {}, 2, 2, 2)

        for i in range(10):
            with self.pool.using(referent):
                pass
            e0.negative_num_uses = -2 - i
            self.assert_pool([e0, e1], {}, 2, 2, 2)

    def test_weakref(self):
        mock_process = self.mock_context.Process.return_value
        mock_process.pid = 1
        mock_process.exitcode = None
        mock_conn = unittest.mock.Mock()
        mock_actor_conn = unittest.mock.Mock()
        self.mock_context.Pipe.return_value = (mock_conn, mock_actor_conn)
        mock_conn.recv_bytes.return_value = pickle.dumps((None, None))
        referent = object()

        self.pool._max_uses_per_actor = None

        a0 = self.pool.get(referent)
        a0_id = id(a0)
        e0 = pools.ProcessActorPool._Entry(
            process=mock_process,
            conn=mock_conn,
            negative_num_uses=-1,
        )
        self.assert_pool([], {a0_id: e0}, 1, 1, 1)

        del a0
        self.assert_pool([e0], {}, 1, 1, 1)

    def test_actor_crash(self):
        mock_process = self.mock_context.Process.return_value
        mock_process.pid = 1
        mock_process.exitcode = 1
        mock_conn = unittest.mock.Mock()
        mock_conn.recv_bytes.return_value = pickle.dumps((None, None))
        mock_actor_conn = unittest.mock.Mock()
        self.mock_context.Pipe.return_value = (mock_conn, mock_actor_conn)
        referent = object()

        self.assert_pool([], {}, 0, 0, 0)

        with self.pool.using(referent) as a:
            e = pools.ProcessActorPool._Entry(
                process=mock_process,
                conn=mock_conn,
                negative_num_uses=-1,
            )
            self.assert_pool([], {id(a): e}, 1, 1, 1)
            self.assert_process(mock_process, 1)
            self.assert_conn(
                mock_conn,
                pools._Call('_adopt', (None, ), {}),
                pools._Call('_adopt', (referent, ), {}),
            )

        self.assert_pool([], {}, 1, 0, 1)
        self.assert_process(mock_process, 3)
        self.assert_conn(
            mock_conn,
            pools._Call('_adopt', (None, ), {}),
            pools._Call('_adopt', (referent, ), {}),
            pools._Call('_disadopt', (), {}),
            None,
        )

    def test_close_non_graceful(self):
        mock_exitcode = unittest.mock.PropertyMock()
        mock_process = self.mock_context.Process.return_value
        mock_process.pid = 1
        type(mock_process).exitcode = mock_exitcode
        mock_conn = unittest.mock.Mock()
        mock_conn.recv_bytes.return_value = pickle.dumps((None, None))
        mock_actor_conn = unittest.mock.Mock()
        self.mock_context.Pipe.return_value = (mock_conn, mock_actor_conn)
        referent = object()

        mock_exitcode.return_value = None

        a1 = self.pool.get(referent)
        with self.pool.using(referent):
            pass
        e = pools.ProcessActorPool._Entry(
            process=mock_process,
            conn=mock_conn,
            negative_num_uses=-1,
        )
        self.assert_pool([e], {id(a1): e}, 2, 2, 2)

        mock_exitcode.return_value = 0

        self.pool.close(False)
        self.assert_pool([], {}, 2, 0, 2)
        self.assertEqual(len(mock_process.kill.mock_calls), 2)
        mock_process.join.assert_has_calls([
            unittest.mock.call(timeout=1),
            unittest.mock.call(timeout=1),
        ])
        self.assertEqual(len(mock_process.close.mock_calls), 2)
        self.assertEqual(len(mock_conn.close.mock_calls), 2)

    def test_actual_pool(self):
        with pools.ProcessActorPool(1) as pool:
            with pool.using(Acc()) as stub:
                self.assertEqual(stub.m.get(), 0)
                self.assertEqual(stub.m.x, 0)


class ProcessActorTest(unittest.TestCase):

    def test_process_actor(self):
        conn, conn_actor = multiprocessing.connection.Pipe()
        process = multiprocessing.Process(
            target=pools._ProcessActor('thread-name', conn_actor),
        )
        process.start()
        try:

            referent = Acc()
            stub = pools._Stub(type(referent), process, conn)
            self.assertIsNone(pools._BoundMethod('_adopt', conn)(referent))

            with self.assertRaisesRegex(
                AssertionError, r'expect not x.startswith\(\'_\'\), not \'_f\''
            ):
                stub.m._f()
            with self.assertRaisesRegex(
                AssertionError, r'expect public method: _f'
            ):
                pools._BoundMethod('_f', conn)(Acc())

            with self.assertRaisesRegex(
                AttributeError, r'\'Acc\' object has no attribute \'f\''
            ):
                stub.m.f()

            self.assertEqual(stub.m.get(), 0)
            self.assertIsNone(stub.m.inc())
            self.assertEqual(stub.m.get(), 1)
            self.assertIsNone(stub.m.inc(3))
            self.assertEqual(stub.m.get(), 4)

            self.assertEqual(stub.m.x, 4)
            self.assertEqual(stub.m.p, 'hello world')
            self.assertEqual(stub.m.cf('foo'), 'foo')
            self.assertEqual(stub.m.sf('bar'), 'bar')
            self.assertEqual(stub.m.g(9), list(range(9)))

            self.assertEqual(stub.submit(func, Acc(), 2, z=3), 5)
            self.assertEqual(stub.apply(func, 10, z=100), 114)

            with self.assertRaisesRegex(
                TypeError, r'cannot pickle \'_io\.BufferedReader\' object'
            ):
                stub.m.not_pickle_able('/dev/null')

            with self.assertRaisesRegex(
                TypeError,
                r'unsupported operand type\(s\) for \+=: '
                r'\'int\' and \'NoneType\'',
            ):
                stub.m.inc(None)

            with tempfile.TemporaryFile() as f:
                f.write(b'hello world')
                f.flush()
                f.seek(0)
                remote_fds = stub.send_fds([f.fileno()])
                self.assertEqual(len(remote_fds), 1)
            self.assertEqual(
                stub.submit(consume_fd, remote_fds[0]),
                b'hello world',
            )
            # stub._conn is still usable after send_fds.
            self.assertEqual(stub.m.get(), 4)

            self.assertIsNone(pools._BoundMethod('_disadopt', conn)())

            with self.assertRaisesRegex(
                AssertionError, r'expect referent not None'
            ):
                stub.m.f()

        finally:
            conn.send_bytes(pickle.dumps(None))
            conn.close()
            conn_actor.close()
            process.join(timeout=1)

        self.assertEqual(process.exitcode, 0)


class Acc:

    def __init__(self):
        self.x = 0

    def inc(self, n=1):
        self.x += n

    def get(self):
        return self.x

    @staticmethod
    def sf(x):
        return x

    @classmethod
    def cf(cls, x):
        return x

    @property
    def p(self):
        return 'hello world'

    @staticmethod
    def g(n):
        for i in range(n):
            yield i

    @staticmethod
    def not_pickle_able(path):
        with open(path, 'rb') as f:
            return f


def func(acc, y, z):
    return acc.x + y + z


def consume_fd(fd):
    with os.fdopen(fd, 'rb') as f:
        return f.read()


if __name__ == '__main__':
    unittest.main()
