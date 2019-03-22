import unittest

import gc
import logging
import logging.handlers
import weakref

from g1.asyncs.kernels import errors
from g1.asyncs.kernels import tasks
from g1.asyncs.kernels import traps

try:
    from g1.threads import futures
    from g1.threads import queues
except ImportError:
    futures = None
    queues = None


class TaskTest(unittest.TestCase):

    def test_del_not_resurrecting(self):

        def func():
            yield

        handler = logging.handlers.MemoryHandler(10)
        logger = logging.getLogger(tasks.__name__)
        logger.addHandler(handler)
        try:
            task = tasks.Task(None, func())
            task_ref = weakref.ref(task)
            task_repr = repr(task)

            del task
            gc.collect()  # Ensure that ``task`` is recycled.

            self.assertIsNone(task_ref())
            self.assertEqual(handler.buffer[0].args, (task_repr, ))

        finally:
            logger.removeHandler(handler)

    def test_get_result(self):

        async def square(x):
            return x * x

        async def raises(exc):
            raise exc

        records = []
        task = tasks.Task(None, square(7))
        task.add_callback(records.append)
        self.assertFalse(task.is_completed())
        self.assertEqual(records, [])
        self.assertIsNone(task.tick(None, None))
        self.assertTrue(task.is_completed())
        self.assertEqual(records, [task])
        self.assertEqual(task.get_result_nonblocking(), 49)
        self.assertIsNone(task.get_exception_nonblocking())
        with self.assertRaises(AssertionError):
            task.tick(None, None)

        task.add_callback(records.append)
        self.assertEqual(records, [task, task])

        task = tasks.Task(None, raises(ValueError('hello')))
        self.assertFalse(task.is_completed())
        self.assertIsNone(task.tick(None, None))
        self.assertTrue(task.is_completed())
        with self.assertRaisesRegex(ValueError, r'hello'):
            task.get_result_nonblocking()
        self.assertIsNotNone(task.get_exception_nonblocking())
        with self.assertRaises(AssertionError):
            task.tick(None, None)

        task = tasks.Task(None, raises(SystemExit))
        self.assertIsNone(task.tick(None, None))
        with self.assertRaises(SystemExit):
            task.get_result_nonblocking()

    def test_trap(self):
        sentinel = object()
        task = tasks.Task(None, traps.join(sentinel))
        self.assertFalse(task.is_completed())

        trap = task.tick(None, None)
        self.assertFalse(task.is_completed())
        self.assertIs(trap.kind, traps.Traps.JOIN)
        self.assertIs(trap.task, sentinel)

        self.assertIsNone(task.tick(None, None))
        self.assertTrue(task.is_completed())

        with self.assertRaises(AssertionError):
            task.tick(None, None)

    def test_cancel(self):
        sentinel = object()
        task = tasks.Task(None, traps.join(sentinel))
        self.assertFalse(task.is_completed())
        self.assertIsNotNone(task.tick(None, None))
        self.assertIsNone(task.tick(None, errors.TaskCancellation))
        self.assertTrue(task.is_completed())
        with self.assertRaises(errors.Cancelled):
            task.get_result_nonblocking()


@unittest.skipIf(futures is None, 'g1.threads.futures unavailable')
class CompletionQeueuTest(unittest.TestCase):

    def test_completion_queue(self):

        async def square(x):
            return x * x

        cq = futures.CompletionQueue()

        t1 = tasks.Task(None, square(5))
        t1.tick(None, None)
        self.assertTrue(t1.is_completed())

        t2 = tasks.Task(None, square(7))
        self.assertFalse(t2.is_completed())

        cq.put(t1)
        cq.put(t2)
        self.assertEqual(len(cq), 2)

        self.assertIs(cq.get(timeout=0), t1)

        with self.assertRaises(queues.Empty):
            cq.get(timeout=0)

        t2.tick(None, None)
        self.assertTrue(t2.is_completed())
        self.assertEqual(len(cq), 1)
        self.assertIs(cq.get(timeout=0), t2)

        self.assertEqual(len(cq), 0)


if __name__ == '__main__':
    unittest.main()
