import unittest

from g1.asyncs import kernels
from g1.asyncs.bases import timers


class TimeoutAfterTest(unittest.TestCase):

    def test_context(self):

        with self.assertRaisesRegex(LookupError, r'ContextVar.*kernel'):
            timers.timeout_after(0)

        @kernels.with_kernel
        def test_with_kernel():
            with self.assertRaisesRegex(LookupError, r'no current task'):
                timers.timeout_after(0)

        test_with_kernel()

    @kernels.with_kernel
    def test_timeout(self):

        async def func(timeout_func, steps):
            steps.append(0)
            with timeout_func(0):
                steps.append(1)
                await timers.sleep(0.001)
                steps.append(2)
            steps.append(3)

        with self.subTest(timers.timeout_after):
            steps = []
            with self.assertRaises(kernels.Timeout):
                kernels.run(func(timers.timeout_after, steps))
            self.assertEqual(steps, [0, 1])

        with self.subTest(timers.timeout_ignore):
            steps = []
            kernels.run(func(timers.timeout_ignore, steps))
            self.assertEqual(steps, [0, 1, 3])

    @kernels.with_kernel
    def test_cancel(self):

        async def func(timeout_func, steps):
            steps.append(0)
            with timeout_func(0) as cancel:
                steps.append(1)
                cancel()
                await timers.sleep(0.001)
                steps.append(2)
            steps.append(3)

        with self.subTest(timers.timeout_after):
            steps = []
            kernels.run(func(timers.timeout_after, steps))
            self.assertEqual(steps, [0, 1, 2, 3])

        with self.subTest(timers.timeout_ignore):
            steps = []
            kernels.run(func(timers.timeout_ignore, steps))
            self.assertEqual(steps, [0, 1, 2, 3])


if __name__ == '__main__':
    unittest.main()
