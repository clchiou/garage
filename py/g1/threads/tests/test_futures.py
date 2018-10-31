import unittest

import sys
import threading

from g1.threads import futures


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
        t = threading.Thread(
            target=futures.wrap_thread_target(sys.exit),
            args=(f, ),
        )
        t.start()
        t.join()
        self.assertTrue(f.is_completed())
        self.assertIsInstance(f.get_exception(), SystemExit)


class CustomError(Exception):
    pass


if __name__ == '__main__':
    unittest.main()
