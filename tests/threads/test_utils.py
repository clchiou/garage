import unittest

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
        self.assertFalse(task_queue.future.cancelled())
        self.assertFalse(task_queue.future.done())

        task_queue.put(1)
        self.assertFalse(task_queue.is_closed())
        self.assertFalse(task_queue.future.done())

        task_queue.put(2)
        self.assertFalse(task_queue.is_closed())
        self.assertFalse(task_queue.future.done())

        self.assertEqual(1, task_queue.get())
        self.assertFalse(task_queue.is_closed())
        self.assertFalse(task_queue.future.done())

        task_queue.notify_task_processed()
        self.assertFalse(task_queue.is_closed())
        self.assertFalse(task_queue.future.done())

        self.assertEqual(2, task_queue.get())
        self.assertFalse(task_queue.is_closed())
        self.assertFalse(task_queue.future.done())

        # This will trigger auto-close.
        task_queue.notify_task_processed()
        self.assertTrue(task_queue.is_closed())
        self.assertTrue(task_queue.future.done())

    def test_priority(self):
        eq = self.assertEqual
        lt = self.assertLess
        gt = self.assertGreater
        test_data = [
            (eq, utils.Priority.LOWEST, utils.Priority.LOWEST),
            (lt, utils.Priority.LOWEST, utils.Priority('x')),
            (lt, utils.Priority.LOWEST, utils.Priority.HIGHEST),

            (eq, utils.Priority('x'), utils.Priority('x')),
            (lt, utils.Priority('x'), utils.Priority('y')),
            (gt, utils.Priority('x'), utils.Priority('w')),
            (gt, utils.Priority('x'), utils.Priority.LOWEST),
            (lt, utils.Priority('x'), utils.Priority.HIGHEST),

            (eq, utils.Priority.HIGHEST, utils.Priority.HIGHEST),
            (gt, utils.Priority.HIGHEST, utils.Priority('x')),
            (gt, utils.Priority.HIGHEST, utils.Priority.LOWEST),
        ]
        for assertion, left, right in test_data:
            assertion(left, right)
            if assertion is eq:
                self.assertEqual(hash(left), hash(right))
            else:
                self.assertNotEqual(hash(left), hash(right))

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


if __name__ == '__main__':
    unittest.main()
