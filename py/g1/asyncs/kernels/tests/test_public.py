import unittest

import threading

from g1.asyncs import kernels


class KernelsTest(unittest.TestCase):

    def test_contexts(self):

        def test_with_kernel():
            self.assertIsNotNone(kernels.get_kernel())

        self.assertIsNone(kernels.get_kernel())
        kernels.call_with_kernel(test_with_kernel)
        self.assertIsNone(kernels.get_kernel())

    def test_nested(self):
        ks = []
        steps = []
        outer(ks, steps)
        self.assert_nested(ks, steps)

    def test_nested_with_threads(self):

        ks1 = []
        steps1 = []

        ks2 = []
        steps2 = []

        t1 = threading.Thread(target=outer, args=(ks1, steps1))
        t2 = threading.Thread(target=outer, args=(ks2, steps2))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assert_nested(ks1, steps1)
        self.assert_nested(ks2, steps2)
        # Different kernels on different threads.
        self.assertIsNot(ks1[0], ks2[0])

    def assert_nested(self, ks, steps):
        self.assertEqual(len(ks), 2)
        self.assertIsNotNone(ks[0])
        self.assertIs(ks[0], ks[1])  # Same kernel per thread.
        self.assertEqual(steps, [1, 2, 3])


@kernels.with_kernel
def outer(ks, steps):
    k = kernels.get_kernel()
    ks.append(k)
    steps.append(1)
    inner(ks, steps)
    steps.append(3)


@kernels.with_kernel
def inner(ks, steps):
    k = kernels.get_kernel()
    ks.append(k)
    steps.append(2)


if __name__ == '__main__':
    unittest.main()
