import unittest
import unittest.mock

from g1.asyncs import kernels
from g1.asyncs.bases import futures
from g1.asyncs.bases import tasks


class FuturesTest(unittest.TestCase):

    @kernels.with_kernel
    def test_future(self):
        future = futures.Future()
        callback = unittest.mock.MagicMock()
        future.add_callback(callback)
        self.assertFalse(future.is_completed())
        callback.assert_not_called()
        with self.assertRaisesRegex(AssertionError, r'expect true'):
            future.get_result_nonblocking()
        with self.assertRaisesRegex(AssertionError, r'expect true'):
            future.get_exception_nonblocking()

        future.set_result(42)
        self.assertTrue(future.is_completed())
        callback.assert_called_once_with(future)
        self.assertEqual(future.get_result_nonblocking(), 42)
        self.assertEqual(kernels.run(future.get_result()), 42)
        self.assertIsNone(future.get_exception_nonblocking())
        self.assertIsNone(kernels.run(future.get_exception()))

        another_callback = unittest.mock.MagicMock()
        future.add_callback(another_callback)
        another_callback.assert_called_once_with(future)

    def test_cancel(self):
        future = futures.Future()
        future.cancel()
        self.assertTrue(future.is_completed())
        self.assertIsInstance(
            future.get_exception_nonblocking(), tasks.Cancelled
        )

    def test_completion_queue(self):
        f1 = futures.Future()
        f2 = futures.Future()
        f3 = futures.Future()
        queue = tasks.CompletionQueue()
        queue.put_nonblocking(f1)
        queue.put_nonblocking(f2)
        queue.put_nonblocking(f3)

        with self.assertRaises(tasks.Empty):
            queue.get_nonblocking()

        f2.set_result(None)
        self.assertIs(queue.get_nonblocking(), f2)
        f3.set_result(None)
        self.assertIs(queue.get_nonblocking(), f3)
        f1.set_result(None)
        self.assertIs(queue.get_nonblocking(), f1)


if __name__ == '__main__':
    unittest.main()
