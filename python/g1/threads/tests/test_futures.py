import unittest

import sys
import threading

from g1.threads import futures
from g1.threads import queues


class FuturesTest(unittest.TestCase):

    def test_add_callback(self):
        calls = []
        f = futures.Future()
        self.assertFalse(f.is_completed())

        f.add_callback(lambda future: calls.append((1, future)))
        self.assertEqual(calls, [])
        f.set_result(42)
        self.assertTrue(f.is_completed())
        self.assertEqual(calls, [(1, f)])

        f.add_callback(lambda future: calls.append((2, future)))
        self.assertEqual(calls, [(1, f), (2, f)])

    def test_add_callback_caller_thread(self):
        calls = []
        f = futures.Future()
        self.assertFalse(f.is_completed())

        f.add_callback(lambda _: calls.append(threading.current_thread()))
        self.assertEqual(calls, [])
        t = threading.Thread(target=f.set_result, args=(42, ))
        t.start()
        t.join()
        self.assertTrue(f.is_completed())
        self.assertEqual(calls, [t])

        f.add_callback(lambda _: calls.append(threading.current_thread()))
        self.assertEqual(calls, [t, threading.current_thread()])

    def test_timeout(self):
        f = futures.Future()
        with self.assertRaises(futures.Timeout):
            f.get_result(timeout=0)
        with self.assertRaises(futures.Timeout):
            f.get_exception(timeout=0)

    def test_set_result(self):
        f = futures.Future()
        self.assertFalse(f.is_completed())
        f.set_result(42)
        self.assertTrue(f.is_completed())
        self.assertEqual(f.get_result(), 42)
        self.assertIsNone(f.get_exception())

    def test_set_result_repeatedly(self):
        f = futures.Future()
        self.assertFalse(f.is_completed())
        f.set_result(42)
        f.set_result(43)  # Ignored.
        f.set_exception(CustomError())  # Ignored.
        self.assertEqual(f.get_result(), 42)
        self.assertIsNone(f.get_exception())

    def test_set_exception(self):
        f = futures.Future()
        self.assertFalse(f.is_completed())
        f.set_exception(CustomError())
        self.assertTrue(f.is_completed())
        with self.assertRaises(CustomError):
            f.get_result()
        self.assertIsInstance(f.get_exception(), CustomError)

    def test_catching_exception_pass(self):
        f = futures.Future()
        with f.catching_exception(reraise=True):
            f.set_result(42)
        self.assertEqual(f.get_result(), 42)
        self.assertIsNone(f.get_exception())

    def test_catching_exception_base_exception(self):

        f = futures.Future()

        def target():
            with f.catching_exception(reraise=True):
                raise SystemExit

        thread = threading.Thread(target=target)
        thread.start()
        thread.join()

        self.assertTrue(f.is_completed())
        self.assertIsInstance(f.get_exception(), SystemExit)

    def test_catching_exception_fail(self):
        f = futures.Future()
        with f.catching_exception(reraise=False):
            raise CustomError
        self.assertIsInstance(f.get_exception(), CustomError)

    def test_wrap_thread_target(self):
        f = futures.Future()
        t = threading.Thread(target=futures.wrap_thread_target(sys.exit, f))
        t.start()
        t.join()
        self.assertTrue(f.is_completed())
        self.assertIsInstance(f.get_exception(), SystemExit)

    def test_finalizer(self):
        lst = []
        f0 = futures.Future()
        f0.set_result(1)
        f0.set_finalizer(lst.append)
        self.assertTrue(f0.is_completed())
        del f0
        self.assertEqual(lst, [1])

        lst.clear()
        f1 = futures.Future()
        f1.set_result(2)
        f1.get_result()
        f1.set_finalizer(lst.append)
        self.assertTrue(f1.is_completed())
        del f1
        self.assertEqual(lst, [])

        f2 = futures.Future()
        f2.set_result(3)
        self.assertTrue(f2.is_completed())
        with self.assertLogs(futures.__name__, level='WARNING') as cm:
            del f2
        self.assertIn(
            'future is garbage-collected but result is never consumed:',
            '\n'.join(cm.output),
        )


class CompletionQueueTest(unittest.TestCase):

    def test_completion_queue(self):
        fs = [futures.Future(), futures.Future(), futures.Future()]
        fs[0].set_result(42)
        cq = futures.CompletionQueue(fs)

        self.assertTrue(cq)
        self.assertEqual(len(cq), 3)
        self.assertFalse(cq.is_closed())

        self.assertEqual(set(cq.as_completed(0)), set(fs[:1]))
        self.assertTrue(cq)
        self.assertEqual(len(cq), 2)

        cq.close()
        self.assertTrue(cq.is_closed())

        fs[1].set_result(42)
        fs[2].set_result(42)
        self.assertEqual(set(cq.as_completed()), set(fs[1:]))

        self.assertFalse(cq)
        self.assertEqual(len(cq), 0)

    def test_close_not_graceful(self):
        f = futures.Future()
        cq = futures.CompletionQueue([f])
        self.assertEqual(cq.close(False), [f])
        with self.assertRaises(queues.Closed):
            cq.get()
        with self.assertRaises(queues.Closed):
            cq.put(f)
        for _ in cq.as_completed():
            self.fail()

    def test_close_repeatedly(self):
        f = futures.Future()
        cq = futures.CompletionQueue([f])
        self.assertFalse(cq.is_closed())
        self.assertEqual(cq.close(True), [])
        self.assertTrue(cq.is_closed())
        self.assertEqual(cq.close(False), [f])
        self.assertTrue(cq.is_closed())
        self.assertEqual(cq.close(True), [])
        self.assertTrue(cq.is_closed())
        self.assertEqual(cq.close(False), [])
        self.assertTrue(cq.is_closed())

    def test_get(self):
        f = futures.Future()
        cq = futures.CompletionQueue([f])

        with self.assertRaises(queues.Empty):
            cq.get(timeout=0)

        cq.close()
        with self.assertRaises(queues.Empty):
            cq.get(timeout=0)

        f.set_result(42)
        self.assertIs(cq.get(timeout=0), f)

        with self.assertRaises(queues.Closed):
            cq.get(timeout=0)

    def test_put(self):
        f = futures.Future()
        cq = futures.CompletionQueue()
        cq.close()
        with self.assertRaises(queues.Closed):
            cq.put(f)

    def test_duplicated_futures(self):
        f = futures.Future()
        cq = futures.CompletionQueue()

        cq.put(f)
        cq.put(f)
        cq.put(f)
        self.assertEqual(len(cq), 3)

        f.set_result(42)
        self.assertIs(cq.get(), f)
        self.assertEqual(len(cq), 2)
        self.assertIs(cq.get(), f)
        self.assertEqual(len(cq), 1)
        self.assertIs(cq.get(), f)
        self.assertEqual(len(cq), 0)

    def test_iter(self):
        fs = [futures.Future() for _ in range(3)]
        f = futures.Future()
        f.set_result(42)
        expect = set(fs)
        expect.add(f)
        cq = futures.CompletionQueue([f])
        actual = set()
        for f in cq:
            actual.add(f)
            if fs:
                f = fs.pop()
                f.set_result(42)
                cq.put(f)
            else:
                cq.close()
        self.assertEqual(actual, expect)

    def test_as_completed(self):
        for timeout in (None, 0):
            with self.subTest(check=timeout):
                fs = [futures.Future() for _ in range(3)]
                f = futures.Future()
                f.set_result(42)
                expect = set(fs)
                expect.add(f)
                cq = futures.CompletionQueue([f])
                # Test putting more futures into the queue while
                # iterating over it.
                actual = set()
                for f in cq.as_completed(timeout):
                    actual.add(f)
                    if fs:
                        f = fs.pop()
                        f.set_result(42)
                        cq.put(f)
                    else:
                        cq.close()
                self.assertEqual(actual, expect)

    def test_as_completed_empty(self):
        cq = futures.CompletionQueue()
        cq.put(futures.Future())
        for _ in cq.as_completed(timeout=0):
            self.fail()
        self.assertEqual(len(cq), 1)

    def test_as_completed_func(self):
        for timeout in (None, 0):
            with self.subTest(check=timeout):
                fs = [futures.Future() for _ in range(3)]
                for f in fs:
                    f.set_result(42)
                actual = set(futures.as_completed(fs, timeout))
                self.assertEqual(actual, set(fs))

    def test_as_completed_func_empty(self):
        for _ in futures.as_completed([futures.Future()], timeout=0):
            self.fail()


class CustomError(Exception):
    pass


if __name__ == '__main__':
    unittest.main()
