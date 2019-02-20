import unittest

from g1.asyncs import kernels


class KernelsTest(unittest.TestCase):

    def test_contexts(self):

        def test_with_kernel():
            self.assertIsNotNone(kernels.get_kernel())

        self.assertIsNone(kernels.get_kernel())
        kernels.call_with_kernel(test_with_kernel)
        self.assertIsNone(kernels.get_kernel())


if __name__ == '__main__':
    unittest.main()
