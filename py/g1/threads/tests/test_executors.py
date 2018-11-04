import unittest

from g1.threads import executors
from g1.threads import queues


class ExecutorsTest(unittest.TestCase):

    def test_executor(self):
        with executors.Executor(3) as executor:
            self.assertEqual(len(executor.stubs), 3)
            self.assertEqual(executor.submit(inc, 1).get_result(), 2)
            f = executor.submit(inc, 'x')
            with self.assertRaises(TypeError):
                f.get_result()
        with self.assertRaises(queues.Closed):
            executor.submit(inc, 1)
        for stub in executor.stubs:
            self.assertTrue(stub.future.is_completed())


def inc(x):
    return x + 1


if __name__ == '__main__':
    unittest.main()
