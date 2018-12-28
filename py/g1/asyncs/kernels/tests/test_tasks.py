import unittest

from g1.asyncs.kernels import errors
from g1.asyncs.kernels import tasks
from g1.asyncs.kernels import traps


class TaskTest(unittest.TestCase):

    def test_get_result(self):

        async def square(x):
            return x * x

        async def raises(exc):
            raise exc

        task = tasks.Task(square(7))
        self.assertFalse(task.is_completed())
        self.assertIsNone(task.tick(None, None))
        self.assertTrue(task.is_completed())
        self.assertEqual(task.get_result_nonblocking(), 49)
        self.assertIsNone(task.get_exception_nonblocking())
        with self.assertRaises(AssertionError):
            task.tick(None, None)

        task = tasks.Task(raises(ValueError('hello')))
        self.assertFalse(task.is_completed())
        self.assertIsNone(task.tick(None, None))
        self.assertTrue(task.is_completed())
        with self.assertRaisesRegex(ValueError, r'hello'):
            task.get_result_nonblocking()
        self.assertIsNotNone(task.get_exception_nonblocking())
        with self.assertRaises(AssertionError):
            task.tick(None, None)

        task = tasks.Task(raises(SystemExit))
        self.assertIsNone(task.tick(None, None))
        with self.assertRaises(SystemExit):
            task.get_result_nonblocking()

    def test_trap(self):
        sentinel = object()
        task = tasks.Task(traps.join(sentinel))
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
        task = tasks.Task(traps.join(sentinel))
        self.assertFalse(task.is_completed())
        self.assertIsNotNone(task.tick(None, None))
        self.assertIsNone(task.tick(None, errors.TaskCancellation))
        self.assertTrue(task.is_completed())
        with self.assertRaises(errors.Cancelled):
            task.get_result_nonblocking()


if __name__ == '__main__':
    unittest.main()
