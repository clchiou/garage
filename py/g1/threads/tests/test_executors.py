import unittest

import threading

try:
    from g1.devtools import tests
except ImportError:
    tests = None

from g1.threads import executors
from g1.threads import queues


class ExecutorTest(unittest.TestCase):

    @unittest.skipUnless(tests, 'g1.tests unavailable')
    def test_del_not_resurrecting(self):
        tests.assert_del_not_resurrecting(self, lambda: executors.Executor(1))

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

    def test_shutdown_graceful(self):
        executor = executors.Executor(4)
        event1 = threading.Event()
        event2 = threading.Event()
        try:

            start_barrier = threading.Barrier(3)

            def func():
                start_barrier.wait()
                event1.wait()

            f1 = executor.submit(func)
            f2 = executor.submit(func)
            f3 = executor.submit(event2.wait)

            start_barrier.wait()

            for stub in executor.stubs:
                self.assertFalse(stub.future.is_completed())

            event2.set()
            self.assertTrue(f3.get_result(timeout=1))

            with self.assertLogs(executors.__name__) as cm:
                items = executor.shutdown(graceful=True, timeout=0.001)

            self.assertEqual(len(cm.output), 1)
            self.assertRegex(cm.output[0], r'not join 2 executor')

            self.assertFalse(f1.is_completed())
            self.assertFalse(f2.is_completed())
            self.assertEqual(items, [])

            counts = {True: 0, False: 0}
            for stub in executor.stubs:
                counts[stub.future.is_completed()] += 1
            self.assertEqual(counts, {True: 2, False: 2})

            event1.set()

            self.assertIsNone(f1.get_result(timeout=1))
            self.assertIsNone(f2.get_result(timeout=1))

            for stub in executor.stubs:
                self.assertTrue(stub.future.is_completed())

        finally:
            event1.set()
            event2.set()
            executor.shutdown()

    def test_shutdown_not_graceful(self):
        executor = executors.Executor(2)
        event = threading.Event()
        try:

            start_barrier = threading.Barrier(3)

            def func():
                start_barrier.wait()
                event.wait()

            f1 = executor.submit(func)
            f2 = executor.submit(func)
            f3 = executor.submit(event.wait)

            start_barrier.wait()

            for stub in executor.stubs:
                self.assertFalse(stub.future.is_completed())

            with self.assertLogs(executors.__name__) as cm:
                items = executor.shutdown(graceful=False)

            self.assertEqual(len(cm.output), 1)
            self.assertRegex(cm.output[0], r'drop 1 tasks')

            self.assertFalse(f1.is_completed())
            self.assertFalse(f2.is_completed())
            self.assertFalse(f3.is_completed())
            self.assertEqual([m.future for m in items], [f3])

            event.set()

            self.assertIsNone(f1.get_result(timeout=1))
            self.assertIsNone(f2.get_result(timeout=1))

            for stub in executor.stubs:
                self.assertTrue(stub.future.is_completed())

        finally:
            event.set()
            executor.shutdown()


class PriorityExecutorTest(unittest.TestCase):

    def test_priority(self):
        actual = []
        b = threading.Barrier(2)
        with executors.PriorityExecutor(1, default_priority=0) as executor:
            executor.submit_with_priority(-1, b.wait)
            fs = [
                executor.submit_with_priority(i, actual.append, i)
                for i in (0, 5, 2, 3, 4, 1)
            ]
            b.wait()
        for f in fs:
            f.get_result()
        self.assertEqual(actual, [0, 1, 2, 3, 4, 5])

    def test_default_priority(self):
        actual = []
        b = threading.Barrier(2)
        with executors.PriorityExecutor(1, default_priority=0) as executor:
            executor.submit(b.wait)
            fs = [
                executor.submit(actual.append, i) for i in (0, 5, 2, 3, 4, 1)
            ]
            b.wait()
        for f in fs:
            f.get_result()
        # Heap order is not stable.
        self.assertEqual(set(actual), {0, 5, 2, 3, 4, 1})

    def test_fifo(self):
        actual = []
        b = threading.Barrier(2)
        with executors.Executor(1) as executor:
            executor.submit(b.wait)
            fs = [
                executor.submit(actual.append, i) for i in (0, 5, 2, 3, 4, 1)
            ]
            b.wait()
        for f in fs:
            f.get_result()
        self.assertEqual(actual, [0, 5, 2, 3, 4, 1])


def inc(x):
    return x + 1


if __name__ == '__main__':
    unittest.main()
