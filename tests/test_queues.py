import unittest

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import garage.queues


class TestQueues(unittest.TestCase):

    def test_queue(self):
        for queue_class, test_input, test_output in [
                (garage.queues.Queue, [1, 2, 3], [1, 2, 3]),
                (garage.queues.PriorityQueue, [1, 3, 2], [1, 2, 3]),
                (garage.queues.LifoQueue, [1, 2, 3], [3, 2, 1])]:
            queue = queue_class()
            for data in test_input:
                queue.put(data)
            for data in test_output:
                self.assertEqual(data, queue.get())

    def test_nonblocking(self):
        queue = garage.queues.Queue(capacity=1)
        self.assertFalse(queue)
        self.assertEqual(0, len(queue))
        self.assertFalse(queue.is_full())

        with self.assertRaises(garage.queues.Empty):
            queue.get(block=False)
        with self.assertRaises(garage.queues.Empty):
            queue.get(block=False, timeout=0.01)

        queue.put(1)
        self.assertTrue(queue)
        self.assertEqual(1, len(queue))
        self.assertTrue(queue.is_full())

        with self.assertRaises(garage.queues.Full):
            queue.put(2, block=False)
        with self.assertRaises(garage.queues.Full):
            queue.put(2, block=False, timeout=0.01)

    def test_close(self):
        queue = garage.queues.Queue()
        self.assertFalse(queue.is_closed())

        queue.put(1)
        queue.put(2)
        queue.put(3)

        self.assertListEqual([1, 2, 3], queue.close())
        self.assertTrue(queue.is_closed())

        self.assertListEqual([], queue.close())

        with self.assertRaises(garage.queues.Closed):
            queue.put(4)
        with self.assertRaises(garage.queues.Closed):
            queue.get()

    def test_close_while_blocked(self):
        queue = garage.queues.Queue()
        for kwargs in [{}, {'timeout': 10}]:
            barrier = threading.Barrier(2)
            with ThreadPoolExecutor(1) as executor:
                future = executor.submit(
                    call_func, barrier, queue.get, kwargs)
                barrier.wait()
                # XXX: I hope that, after sleep, the executor thread is
                # blocked inside get() or it will raise Empty.
                time.sleep(0.01)
                queue.close()
                with self.assertRaises(garage.queues.Closed):
                    future.result()

        queue = garage.queues.Queue(capacity=1)
        queue.put(1)  # Make it full.
        for kwargs in [{'item': 1}, {'item': 1, 'timeout': 10}]:
            barrier = threading.Barrier(2)
            with ThreadPoolExecutor(1) as executor:
                future = executor.submit(
                    call_func, barrier, queue.put, kwargs)
                barrier.wait()
                # XXX: I hope that, after sleep, the executor thread is
                # blocked inside put() or it will raise Full.
                time.sleep(0.01)
                queue.close()
                with self.assertRaises(garage.queues.Closed):
                    future.result()


def call_func(barrier, func, kwargs):
    barrier.wait()
    func(**kwargs)


if __name__ == '__main__':
    unittest.main()
