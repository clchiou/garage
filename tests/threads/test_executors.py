import unittest

import threading

from garage.threads import executors


class TestExecutor(unittest.TestCase):

    def test_executor(self):
        pool = executors.WorkerPool()
        self.assertEqual(0, len(pool))

        # No jobs, no workers are hired.
        with executors.Executor(pool, 1) as executor:
            self.assertEqual(0, len(pool))

        self.assertEqual(0, len(pool))

        with executors.Executor(pool, 1) as executor:
            f1 = executor.submit(sum, (1, 2, 3))
            f2 = executor.submit(sum, (4, 5, 6))
            self.assertEqual(0, len(pool))
            self.assertEqual(6, f1.result())
            self.assertEqual(15, f2.result())

        self.assertEqual(1, len(pool))

        for worker in pool:
            self.assertFalse(worker.get_future().done())

    def test_shutdown(self):
        pool = executors.WorkerPool()
        self.assertEqual(0, len(pool))

        with executors.Executor(pool, 1) as executor:
            f1 = executor.submit(sum, (1, 2, 3))
            f2 = executor.submit(sum, (4, 5, 6))
            self.assertEqual(0, len(pool))
            self.assertEqual(6, f1.result())
            self.assertEqual(15, f2.result())
            executor.shutdown(wait=False)

        # shutdown(wait=False) does not return workers to the pool.
        self.assertEqual(0, len(pool))

        event = threading.Event()
        with executors.Executor(pool, 1) as executor:
            executor.submit(event.wait)
            executor.shutdown(wait=False)
            self.assertFalse(executor._work_queue)


if __name__ == '__main__':
    unittest.main()
