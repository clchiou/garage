import unittest
import unittest.mock

from g1.threads import queues


class QueuesTest(unittest.TestCase):

    def test_queue(self):
        checks = [
            (queues.Queue, [1, 2, 3], [1, 2, 3]),
            (queues.PriorityQueue, [1, 3, 2], [1, 2, 3]),
            (queues.LifoQueue, [1, 2, 3], [3, 2, 1]),
        ]
        for cls, test_input, expect in checks:
            with self.subTest(check=cls.__name__):
                queue = cls()
                self.assertFalse(queue)
                for item in test_input:
                    queue.put(item)
                self.assertTrue(queue)
                self.assertEqual(len(queue), len(test_input))
                self.assertFalse(queue.is_full())
                self.assertFalse(queue.is_closed())
                actual = []
                while queue:
                    actual.append(queue.get())
                self.assertEqual(actual, expect)

    @unittest.mock.patch('time.perf_counter')
    def test_timeout(self, perf_counter):
        seconds = []
        perf_counter.side_effect = lambda: seconds.pop(0)

        queue = queues.Queue(capacity=1)
        self.assertFalse(queue.is_full())

        seconds[:] = []
        with self.assertRaises(queues.Empty):
            queue.get(timeout=0)

        seconds[:] = [0, 1.01]
        with self.assertRaises(queues.Empty):
            queue.get(timeout=1)

        queue.put(42)
        self.assertTrue(queue.is_full())

        seconds[:] = []
        with self.assertRaises(queues.Full):
            queue.put(43, timeout=0)

        seconds[:] = [0, 1.01]
        with self.assertRaises(queues.Full):
            queue.put(43, timeout=1)

    def test_close(self):
        queue = queues.Queue()
        self.assertFalse(queue.is_closed())

        queue.put(42)
        queue.put(43)
        queue.put(44)

        self.assertEqual(queue.close(), [])
        self.assertTrue(queue.is_closed())
        self.assertTrue(queue)

        self.assertEqual(queue.close(), [])

        with self.assertRaises(queues.Closed):
            queue.put(45, timeout=None)
        with self.assertRaises(queues.Closed):
            queue.put(45, timeout=0)
        with self.assertRaises(queues.Closed):
            queue.put(45, timeout=1)

        actual = []
        while queue:
            actual.append(queue.get())
        self.assertEqual(actual, [42, 43, 44])

        with self.assertRaises(queues.Closed):
            queue.get(timeout=None)
        with self.assertRaises(queues.Closed):
            queue.get(timeout=0)
        with self.assertRaises(queues.Closed):
            queue.get(timeout=1)

    def test_close_not_graceful(self):
        queue = queues.Queue()
        self.assertFalse(queue.is_closed())

        queue.put(42)
        queue.put(43)
        queue.put(44)

        self.assertEqual(queue.close(False), [42, 43, 44])
        self.assertTrue(queue.is_closed())
        self.assertFalse(queue)


class WaiterTest(unittest.TestCase):

    def test_blocking_wait(self):
        condition = unittest.mock.Mock()
        wait = queues.make_waiter(condition, None)
        self.assertTrue(wait())
        condition.wait.assert_called_once()

    def test_nonblocking_wait(self):
        condition = unittest.mock.Mock()
        wait = queues.make_waiter(condition, 0)
        self.assertFalse(wait())
        condition.wait.assert_not_called()

    @unittest.mock.patch('time.perf_counter')
    def test_timed_wait(self, perf_counter):
        seconds = [0, 12, 34, 56, 101]
        perf_counter.side_effect = lambda: seconds.pop(0)
        condition = unittest.mock.Mock()
        wait = queues.make_waiter(condition, 100)

        self.assertTrue(wait())
        self.assertTrue(wait())
        self.assertTrue(wait())
        self.assertFalse(wait())

        condition.wait.assert_has_calls([
            unittest.mock.call(88),
            unittest.mock.call(66),
            unittest.mock.call(44),
        ])
        self.assertEqual(seconds, [])

    @unittest.mock.patch('time.perf_counter')
    def test_timed_wait_overflowed(self, perf_counter):
        seconds = [0.0, -1.1]
        perf_counter.side_effect = lambda: seconds.pop(0)
        condition = unittest.mock.Mock()
        wait = queues.make_waiter(condition, 1.0)
        self.assertFalse(wait())
        condition.wait.assert_not_called()
        self.assertEqual(seconds, [])


if __name__ == '__main__':
    unittest.main()
