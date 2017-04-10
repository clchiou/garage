import unittest

import heapq
import random
import threading

from garage.threads import queues
from garage.threads import utils


class UtilsTest(unittest.TestCase):

    def test_atomic_int(self):
        i = utils.AtomicInt()
        self.assertEqual(0, i.get_and_add(0))
        self.assertEqual(0, i.get_and_add(1))
        self.assertEqual(1, i.get_and_add(2))
        self.assertEqual(3, i.get_and_add(3))
        self.assertEqual(6, i.get_and_add(4))
        self.assertEqual(10, i.get_and_add(0))

        self.assertEqual(10, i.get_and_set(-1))
        self.assertEqual(-1, i.get_and_set(2))
        self.assertEqual(2, i.get_and_set(0))

    def test_atomic_set(self):
        s = utils.AtomicSet()
        self.assertFalse('x' in s)
        self.assertFalse(s.check_and_add('x'))
        self.assertTrue('x' in s)
        self.assertFalse(s.check_and_add('y'))
        self.assertTrue('y' in s)

    def test_task_queue(self):
        task_queue = utils.TaskQueue(queues.Queue())
        self.assertFalse(task_queue.is_closed())

        task_queue.put(1)
        self.assertFalse(task_queue.is_closed())

        task_queue.put(2)
        self.assertFalse(task_queue.is_closed())

        self.assertEqual(1, task_queue.get())
        self.assertFalse(task_queue.is_closed())

        task_queue.notify_task_processed()
        self.assertFalse(task_queue.is_closed())

        self.assertEqual(2, task_queue.get())
        self.assertFalse(task_queue.is_closed())

        # This will trigger auto-close.
        task_queue.notify_task_processed()
        self.assertTrue(task_queue.is_closed())

    def test_priority(self):
        with self.assertRaises(AssertionError):
            utils.Priority([])  # Non-hashable!

        eq = self.assertEqual
        lt = self.assertLess
        gt = self.assertGreater
        test_data = [
            (eq, utils.Priority.LOWEST, utils.Priority.LOWEST),
            (gt, utils.Priority.LOWEST, utils.Priority('x')),
            (gt, utils.Priority.LOWEST, utils.Priority.HIGHEST),

            (eq, utils.Priority('x'), utils.Priority('x')),
            (lt, utils.Priority('x'), utils.Priority('y')),
            (gt, utils.Priority('x'), utils.Priority('w')),
            (lt, utils.Priority('x'), utils.Priority.LOWEST),
            (gt, utils.Priority('x'), utils.Priority.HIGHEST),

            (eq, utils.Priority.HIGHEST, utils.Priority.HIGHEST),
            (lt, utils.Priority.HIGHEST, utils.Priority('x')),
            (lt, utils.Priority.HIGHEST, utils.Priority.LOWEST),
        ]
        for assertion, left, right in test_data:
            assertion(left, right)
            if assertion is eq:
                self.assertEqual(hash(left), hash(right))
            else:
                self.assertNotEqual(hash(left), hash(right))

    def test_priority_with_heap(self):

        def heapsort(iterable):
            heap = []
            for value in iterable:
                heapq.heappush(heap, value)
            return [heapq.heappop(heap) for _ in range(len(heap))]

        random.seed(4)

        for expect in (
                [],
                [utils.Priority(0)],
                [utils.Priority.HIGHEST],
                [utils.Priority.LOWEST],

                [utils.Priority(0), utils.Priority(0)],
                [utils.Priority(0), utils.Priority(1)],
                [utils.Priority(0), utils.Priority.LOWEST],
                [utils.Priority.HIGHEST, utils.Priority(0)],
                [utils.Priority.HIGHEST, utils.Priority.LOWEST],

                [utils.Priority(0), utils.Priority(0), utils.Priority(0)],
                [utils.Priority(0), utils.Priority(1), utils.Priority(2)],
                [utils.Priority(0), utils.Priority(1), utils.Priority.LOWEST],
                [utils.Priority.HIGHEST, utils.Priority(0), utils.Priority(1)],
                [
                    utils.Priority.HIGHEST,
                    utils.Priority(0),
                    utils.Priority.LOWEST,
                ],
                ):

            actual = list(expect)
            random.shuffle(actual)
            actual = heapsort(actual)
            self.assertListEqual(expect, actual)

            actual = heapsort((reversed(expect)))
            self.assertListEqual(expect, actual)

    def test_generate_names(self):
        names = utils.generate_names(name='hello')
        self.assertEqual('hello-01', next(names))
        self.assertEqual('hello-02', next(names))
        self.assertEqual('hello-03', next(names))

        names = utils.generate_names(
            name_format='{string}-{serial}',
            string='hello',
            serial=utils.AtomicInt(0))
        self.assertEqual('hello-0', next(names))
        self.assertEqual('hello-1', next(names))
        self.assertEqual('hello-2', next(names))

    def test_make_get_thread_local(self):

        # They should access the same 'x'
        get_x_1 = utils.make_get_thread_local(
            'x', lambda: threading.current_thread().ident)
        get_x_2 = utils.make_get_thread_local(
            'x', lambda: self.fail('this should not be called'))

        def func(x_output):
            x_output.append(get_x_1())
            x_output.append(get_x_2())

        t1_x = []
        t1 = threading.Thread(target=func, args=(t1_x,))
        t1.start()

        t2_x = []
        t2 = threading.Thread(target=func, args=(t2_x,))
        t2.start()

        t1.join()
        t2.join()

        self.assertEqual([t1.ident, t1.ident], t1_x)
        self.assertEqual([t2.ident, t2.ident], t2_x)


if __name__ == '__main__':
    unittest.main()
