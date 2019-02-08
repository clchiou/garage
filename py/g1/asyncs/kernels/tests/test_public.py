import unittest

from g1.asyncs import kernels


class KernelsTest(unittest.TestCase):
    """Test ``g1.asyncs.kernels`` public interface."""

    def test_contexts(self):

        self.assertIsNone(kernels.get_kernel())
        self.assertEqual(kernels.get_all_tasks(), [])
        self.assertIsNone(kernels.get_current_task())

        def test_with_kernel():
            self.assertIsNotNone(kernels.get_kernel())

            task = kernels.spawn(noop)
            self.assertEqual(kernels.get_all_tasks(), [task])

            kernels.run(timeout=1)
            self.assertEqual(kernels.get_all_tasks(), [])

        kernels.call_with_kernel(test_with_kernel)

        self.assertIsNone(kernels.get_kernel())
        self.assertEqual(kernels.get_all_tasks(), [])
        self.assertIsNone(kernels.get_current_task())

    def test_timeout_after(self):

        with self.assertRaisesRegex(LookupError, r'ContextVar.*kernel'):
            kernels.timeout_after(0)

        @kernels.with_kernel
        def test_with_kernel():
            with self.assertRaisesRegex(LookupError, r'no current task'):
                kernels.timeout_after(0)

        test_with_kernel()


async def noop():
    pass


if __name__ == '__main__':
    unittest.main()
