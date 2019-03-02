import unittest

from g1.asyncs import kernels
from g1.asyncs.bases import queues


class QueuesTest(unittest.TestCase):

    def test_queue_without_kernel(self):
        self.assertIsNone(kernels.get_kernel())
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
                    queue.put_nonblocking(item)
                self.assertTrue(queue)
                self.assertEqual(len(queue), len(test_input))
                self.assertFalse(queue.is_full())
                self.assertFalse(queue.is_closed())
                actual = []
                while queue:
                    actual.append(queue.get_nonblocking())
                self.assertEqual(actual, expect)

    @kernels.with_kernel
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
                    kernels.run(queue.put(item))
                self.assertTrue(queue)
                self.assertEqual(len(queue), len(test_input))
                self.assertFalse(queue.is_full())
                self.assertFalse(queue.is_closed())
                actual = []
                while queue:
                    actual.append(kernels.run(queue.get()))
                self.assertEqual(actual, expect)

    @kernels.with_kernel
    def test_capacity(self):
        queue = queues.Queue(3)
        self.assertFalse(queue.is_closed())

        for x in (42, 43, 44):
            self.assertFalse(queue.is_full())
            kernels.run(queue.put(x))
        self.assertTrue(queue.is_full())

        with self.assertRaises(queues.Full):
            queue.put_nonblocking(45)
        self.assertTrue(queue.is_full())

        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(queue.put(45), timeout=0)
        self.assertTrue(queue.is_full())

        self.assertEqual(kernels.run(queue.get()), 42)
        self.assertFalse(queue.is_full())

        kernels.run()

        actual = []
        while queue:
            actual.append(kernels.run(queue.get()))
        self.assertEqual(actual, [43, 44, 45])

    @kernels.with_kernel
    def test_close(self):
        queue = queues.Queue()
        self.assertFalse(queue.is_closed())

        for x in (42, 43, 44):
            kernels.run(queue.put(x))

        self.assertEqual(queue.close(), [])
        self.assertTrue(queue.is_closed())
        self.assertTrue(queue)

        self.assertEqual(queue.close(), [])

        with self.assertRaises(queues.Closed):
            kernels.run(queue.put(45))
        with self.assertRaises(queues.Closed):
            queue.put_nonblocking(45)

        actual = []
        while queue:
            actual.append(kernels.run(queue.get()))
        self.assertEqual(actual, [42, 43, 44])

        with self.assertRaises(queues.Closed):
            kernels.run(queue.get())
        with self.assertRaises(queues.Closed):
            queue.get_nonblocking()

    @kernels.with_kernel
    def test_close_not_graceful(self):
        queue = queues.Queue()
        self.assertFalse(queue.is_closed())

        for x in (42, 43, 44):
            kernels.run(queue.put(x))

        self.assertEqual(queue.close(False), [42, 43, 44])
        self.assertTrue(queue.is_closed())
        self.assertFalse(queue)

    @kernels.with_kernel
    def test_close_repeatedly(self):
        queue = queues.Queue()
        self.assertFalse(queue.is_closed())

        for x in (42, 43, 44):
            kernels.run(queue.put(x))

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
