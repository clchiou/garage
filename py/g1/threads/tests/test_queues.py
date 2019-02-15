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

    @unittest.mock.patch('time.monotonic')
    def test_timeout(self, monotonic_mock):

        queue = queues.Queue(capacity=1)
        self.assertFalse(queue.is_full())

        monotonic_mock.side_effect = []
        with self.assertRaises(queues.Empty):
            queue.get(timeout=0)

        monotonic_mock.side_effect = [0, 11]
        with self.assertRaises(queues.Empty):
            queue.get(timeout=10)

        queue.put(42)
        self.assertTrue(queue.is_full())

        monotonic_mock.side_effect = []
        with self.assertRaises(queues.Full):
            queue.put(43, timeout=0)

        monotonic_mock.side_effect = [0, 11]
        with self.assertRaises(queues.Full):
            queue.put(43, timeout=10)

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

    def test_close_repeatedly(self):
        queue = queues.Queue()
        self.assertFalse(queue.is_closed())

        queue.put(42)
        queue.put(43)
        queue.put(44)

        self.assertEqual(queue.close(True), [])
        self.assertTrue(queue.is_closed())
        self.assertEqual(queue.close(False), [42, 43, 44])
        self.assertTrue(queue.is_closed())
        self.assertEqual(queue.close(True), [])
        self.assertTrue(queue.is_closed())
        self.assertEqual(queue.close(False), [])
        self.assertTrue(queue.is_closed())


if __name__ == '__main__':
    unittest.main()
