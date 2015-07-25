import unittest

import garage.executor


class TestExecutor(unittest.TestCase):

    def test_executor(self):
        pool = garage.executor.WorkerPool()
        self.assertEqual(0, len(pool))

        # No jobs, no workers are hired.
        with garage.executor.Executor(pool, 1) as executor:
            self.assertEqual(0, len(pool))

        self.assertEqual(0, len(pool))

        with garage.executor.Executor(pool, 1) as executor:
            f1 = executor.submit(sum, (1, 2, 3))
            f2 = executor.submit(sum, (4, 5, 6))
            self.assertEqual(0, len(pool))
            self.assertEqual(6, f1.result())
            self.assertEqual(15, f2.result())

        self.assertEqual(1, len(pool))

        for worker in pool:
            self.assertFalse(worker.is_busy())
            self.assertFalse(worker.is_dead())


if __name__ == '__main__':
    unittest.main()
