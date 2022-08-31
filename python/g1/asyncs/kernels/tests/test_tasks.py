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
        self.assertIsNot(task._coroutine, tasks._SENTINEL)
        self.assertEqual(records, [])
        self.assertIsNone(task.tick(None, None))
        self.assertTrue(task.is_completed())
        self.assertIs(task._coroutine, tasks._SENTINEL)
        self.assertEqual(records, [task])
        self.assertEqual(task.get_result_nonblocking(), 49)
        self.assertIsNone(task.get_exception_nonblocking())
        with self.assertRaises(AssertionError):
            task.tick(None, None)

        task.add_callback(records.append)
        self.assertEqual(records, [task, task])

        task = tasks.Task(None, raises(ValueError('hello')))
        self.assertFalse(task.is_completed())
        self.assertIsNot(task._coroutine, tasks._SENTINEL)
        self.assertIsNone(task.tick(None, None))
        self.assertTrue(task.is_completed())
        self.assertIs(task._coroutine, tasks._SENTINEL)
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
        self.assertIsNot(task._coroutine, tasks._SENTINEL)

        trap = task.tick(None, None)
        self.assertFalse(task.is_completed())
        self.assertIsNot(task._coroutine, tasks._SENTINEL)
        self.assertIs(trap.kind, traps.Traps.JOIN)
        self.assertIs(trap.task, sentinel)

        self.assertIsNone(task.tick(None, None))
        self.assertTrue(task.is_completed())
        self.assertIs(task._coroutine, tasks._SENTINEL)

        with self.assertRaises(AssertionError):
            task.tick(None, None)

    def test_cancel(self):
        sentinel = object()
        task = tasks.Task(None, traps.join(sentinel))
        self.assertFalse(task.is_completed())
        self.assertIsNot(task._coroutine, tasks._SENTINEL)
        self.assertIsNotNone(task.tick(None, None))
        self.assertIsNone(task.tick(None, errors.TaskCancellation))
        self.assertTrue(task.is_completed())
        self.assertIs(task._coroutine, tasks._SENTINEL)
        with self.assertRaises(errors.Cancelled):
            task.get_result_nonblocking()

    def test_abort(self):

        raised = False
        called = []

        async def f():
            nonlocal raised
            try:
                while True:
                    await traps.join(object())
            except GeneratorExit:
                raised = True
                raise

        task = tasks.Task(None, f())
        task.add_callback(lambda _: called.append(True))
        task.tick(None, None)
        self.assertFalse(task.is_completed())
        self.assertIsNot(task._coroutine, tasks._SENTINEL)
        self.assertFalse(raised)
        self.assertEqual(called, [])

        task.abort()

        self.assertTrue(task.is_completed())
        self.assertIs(task._coroutine, tasks._SENTINEL)
        self.assertIsInstance(
            task.get_exception_nonblocking(), errors.Cancelled
        )
        self.assertTrue(raised)
        self.assertEqual(called, [True])

    def test_abort_reraise(self):

        raised = False
        called = []

        async def f():
            nonlocal raised
            try:
                while True:
                    await traps.join(object())
            except GeneratorExit:
                raised = True
                raise ValueError from None

        task = tasks.Task(None, f())
        task.add_callback(lambda _: called.append(True))
        task.tick(None, None)
        self.assertFalse(task.is_completed())
        self.assertIsNot(task._coroutine, tasks._SENTINEL)
        self.assertFalse(raised)
        self.assertEqual(called, [])

        task.abort()

        self.assertTrue(task.is_completed())
        self.assertIs(task._coroutine, tasks._SENTINEL)
        self.assertIsInstance(task.get_exception_nonblocking(), ValueError)
        self.assertTrue(raised)
        self.assertEqual(called, [True])

    def test_abort_blocked(self):

        done = False
        exited = False
        called = []

        async def f():
            nonlocal exited
            try:
                while not done:
                    try:
                        await traps.join(object())
                    except GeneratorExit:
                        pass
            finally:
                exited = True

        task = tasks.Task(None, f())
        task.add_callback(lambda _: called.append(True))
        task.tick(None, None)
        self.assertFalse(task.is_completed())
        self.assertIsNot(task._coroutine, tasks._SENTINEL)
        self.assertFalse(exited)
        self.assertEqual(called, [])

        with self.assertLogs(tasks.__name__, level='WARNING') as cm:
            task.abort()

        self.assertIn('task cannot be aborted', '\n'.join(cm.output))
        self.assertFalse(task.is_completed())
        self.assertIsNot(task._coroutine, tasks._SENTINEL)
        self.assertFalse(exited)
        self.assertEqual(called, [])

        done = True
        task.abort()
        self.assertTrue(task.is_completed())
        self.assertIs(task._coroutine, tasks._SENTINEL)
        self.assertIsInstance(
            task.get_exception_nonblocking(), errors.Cancelled
        )
        self.assertTrue(exited)
        self.assertEqual(called, [True])


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
