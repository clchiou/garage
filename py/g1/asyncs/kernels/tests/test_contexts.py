import unittest

from g1.asyncs.kernels import contexts


class ContextsTest(unittest.TestCase):

    def test_kernel(self):
        with self.assertRaises(LookupError):
            contexts.get_kernel()
        token = contexts.set_kernel(42)
        self.assertEqual(contexts.get_kernel(), 42)
        contexts.KERNEL.reset(token)
        with self.assertRaises(LookupError):
            contexts.get_kernel()

    def test_task(self):
        with self.assertRaises(LookupError):
            contexts.get_current_task()
        with contexts.setting_current_task(42):
            self.assertEqual(contexts.get_current_task(), 42)
        with self.assertRaises(LookupError):
            contexts.get_current_task()


if __name__ == '__main__':
    unittest.main()
