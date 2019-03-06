import unittest

from g1.asyncs.kernels import blockers
from g1.asyncs.kernels import tasks


class ForeverBlockerTest(unittest.TestCase):

    def setUp(self):
        self.b = blockers.ForeverBlocker()

    def assert_state(self, task_set):
        self.assertEqual(bool(self.b), bool(task_set))
        self.assertEqual(len(self.b), len(task_set))
        self.assertEqual(set(self.b), task_set)

    def test_blocker(self):
        self.assert_state(set())

        self.b.block('1', 1)
        self.assert_state({1})

        self.b.block('2', 1)
        self.assert_state({1})

        self.assertFalse(self.b.unblock('1'))
        self.assert_state({1})

        self.assertFalse(self.b.unblock('2'))
        self.assert_state({1})

        self.assertFalse(self.b.cancel(0))
        self.assert_state({1})

        self.assertTrue(self.b.cancel(1))
        self.assert_state(set())


class TaskCompletionBlockerTest(unittest.TestCase):

    def setUp(self):

        async def func():
            pass

        self.t1 = tasks.Task(None, func())
        self.t2 = tasks.Task(None, func())
        self.t3 = tasks.Task(None, func())
        self.t4 = tasks.Task(None, func())
        self.t5 = tasks.Task(None, func())
        self.ts = [self.t1, self.t2, self.t3, self.t4, self.t5]

        self.b = blockers.TaskCompletionBlocker()

    def tearDown(self):
        for task in self.ts:
            if not task.is_completed():
                task.tick(None, None)

    def assert_blocker(self, num_tasks):
        self.assertEqual(bool(self.b), num_tasks > 0)
        self.assertEqual(len(self.b), num_tasks)
        self.assertEqual(
            sum(map(len, self.b._source_to_tasks.values())),
            num_tasks,
        )
        if num_tasks == 0:
            self.assertFalse(self.b._source_to_tasks)

    def test_blocker(self):

        num_tasks = 0
        self.assert_blocker(num_tasks)

        with self.assertRaises(AssertionError):
            self.b.block(self.t1, self.t1)
        self.assert_blocker(num_tasks)

        self.assertEqual(self.b.get_num_blocked_on(self.t1), 0)
        for task in (self.t2, self.t3):
            self.b.block(self.t1, task)
            num_tasks += 1
            self.assert_blocker(num_tasks)
        self.assertEqual(self.b.get_num_blocked_on(self.t1), 2)

        self.assertEqual(self.b.get_num_blocked_on(self.t2), 0)
        for task in (self.t4, self.t5):
            self.b.block(self.t2, task)
            num_tasks += 1
            self.assert_blocker(num_tasks)
        self.assertEqual(self.b.get_num_blocked_on(self.t2), 2)

        self.assertEqual(self.b.unblock(self.t3), ())
        self.assert_blocker(num_tasks)

        self.assertEqual(self.b.unblock(self.t2), {self.t4, self.t5})
        self.assertEqual(self.b.unblock(self.t2), ())
        num_tasks -= 2
        self.assert_blocker(num_tasks)

        self.assertEqual(self.b.unblock(self.t1), {self.t2, self.t3})
        self.assertEqual(self.b.unblock(self.t1), ())
        num_tasks -= 2
        self.assert_blocker(num_tasks)

        self.assertEqual(num_tasks, 0)

    def test_completed_tasks(self):
        self.t1.tick(None, None)
        self.assertTrue(self.t1.is_completed())
        with self.assertRaises(AssertionError):
            self.b.block(self.t1, self.t2)

    def test_cancel(self):

        num_tasks = 0
        self.assert_blocker(num_tasks)

        self.b.block(self.t2, self.t1)
        num_tasks += 1
        self.assert_blocker(num_tasks)

        with self.assertRaises(AssertionError):
            self.b.block(self.t3, self.t1)
        self.assert_blocker(num_tasks)

        self.assertIs(self.b.cancel(self.t1), self.t2)
        num_tasks -= 1
        self.assert_blocker(num_tasks)

        self.assertIsNone(self.b.cancel(self.t1))
        self.assert_blocker(num_tasks)


class TimeoutBlockerTest(unittest.TestCase):

    def assert_blocker(self, blocker, num_tasks, num_queue_items):
        self.assertEqual(bool(blocker), num_tasks > 0)
        self.assertEqual(len(blocker), num_tasks)
        self.assertEqual(len(blocker._tasks), num_tasks)
        self.assertEqual(len(blocker._queue), num_queue_items)

    def test_blocker(self):

        t1 = frozenset([1])
        t2 = frozenset([2])
        t3 = frozenset([3])
        t4 = frozenset([4])
        t5 = frozenset([5])

        b = blockers.TimeoutBlocker()
        num_tasks = 0
        num_queue_items = 0
        self.assert_blocker(b, num_tasks, num_queue_items)

        for s, t in [(1, t1), (5, t2), (2, t3), (4, t4), (3, t5)]:
            b.block(s, t)
            num_tasks += 1
            num_queue_items += 1
            self.assert_blocker(b, num_tasks, num_queue_items)

        self.assertEqual(b.unblock(0), [])
        self.assert_blocker(b, num_tasks, num_queue_items)

        self.assertEqual(b.get_min_timeout(0), 1)

        testdata = [
            (2.5, [t1, t3], 3),
            (4.5, [t5, t4], 5),
            (5, [t2], None),
        ]
        for s, ts, min_t in testdata:
            self.assertEqual(b.unblock(s), ts)
            num_tasks -= len(ts)
            num_queue_items -= len(ts)
            self.assert_blocker(b, num_tasks, num_queue_items)
            self.assertEqual(b.get_min_timeout(0), min_t)

        self.assertEqual(b.unblock(0), [])
        self.assert_blocker(b, num_tasks, num_queue_items)

        self.assertIsNone(b.get_min_timeout(0))

    def test_same_source(self):

        t1 = frozenset([1])
        t2 = frozenset([2])
        t3 = frozenset([3])

        b = blockers.TimeoutBlocker()
        num_tasks = 0
        num_queue_items = 0
        self.assert_blocker(b, num_tasks, num_queue_items)

        for t in [t1, t2]:
            b.block(1, t)
            num_tasks += 1
            num_queue_items += 1
            self.assert_blocker(b, num_tasks, num_queue_items)
        b.block(2, t3)
        self.assert_blocker(b, 3, 3)

        self.assertEqual(set(b.unblock(1)), {t1, t2})
        self.assert_blocker(b, 1, 1)

    def test_cancel(self):

        t1 = frozenset([1])
        t2 = frozenset([2])
        t3 = frozenset([3])
        t4 = frozenset([4])
        t5 = frozenset([5])

        b = blockers.TimeoutBlocker()
        num_tasks = 0
        num_queue_items = 0
        self.assert_blocker(b, num_tasks, num_queue_items)

        for s, t in [(1, t1), (5, t2), (2, t3), (4, t4), (3, t5)]:
            b.block(s, t)
            num_tasks += 1
            num_queue_items += 1
            self.assert_blocker(b, num_tasks, num_queue_items)

        testdata = [
            (1.5, t1, 1, 2),
            (2.5, t3, 2, 3),
            (3.5, t5, 3, 4),
            (4.5, t4, 4, 5),
            (5.5, t2, 5, None),
        ]
        for s, t, min_t_before, min_t_after in testdata:

            self.assertEqual(b.get_min_timeout(0), min_t_before)

            self.assertTrue(b.cancel(t))
            self.assertFalse(b.cancel(t))
            num_tasks -= 1
            self.assert_blocker(b, num_tasks, num_queue_items)
            self.assertEqual(b.get_min_timeout(0), min_t_before)

            self.assertEqual(b.unblock(s), [])
            num_queue_items -= 1
            self.assert_blocker(b, num_tasks, num_queue_items)
            self.assertEqual(b.get_min_timeout(0), min_t_after)

        self.assert_blocker(b, 0, 0)
        self.assertIsNone(b.get_min_timeout(0))


if __name__ == '__main__':
    unittest.main()
