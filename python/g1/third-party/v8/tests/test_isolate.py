import unittest

import contextlib
import threading

from g1.threads import futures

import v8


class IsolateTest(unittest.TestCase):

    def test_num_alive(self):
        self.assertEqual(v8.Isolate.num_alive, 0)

        with v8.Isolate() as i1:
            self.assertEqual(v8.Isolate.num_alive, 1)

            with self.assertRaisesRegex(
                RuntimeError,
                r'this context manager only allows being entered once',
            ):
                i1.__enter__()
            self.assertEqual(v8.Isolate.num_alive, 1)

            with i1.scope():
                self.assertEqual(v8.Isolate.num_alive, 1)
                with i1.scope():
                    self.assertEqual(v8.Isolate.num_alive, 1)
                self.assertEqual(v8.Isolate.num_alive, 1)
            self.assertEqual(v8.Isolate.num_alive, 1)

            with v8.Isolate():
                self.assertEqual(v8.Isolate.num_alive, 2)

            self.assertEqual(v8.Isolate.num_alive, 1)

        self.assertEqual(v8.Isolate.num_alive, 0)

        with self.assertRaisesRegex(
            RuntimeError,
            r'this context manager only allows being entered once',
        ):
            i1.__enter__()
        self.assertEqual(v8.Isolate.num_alive, 0)

    def test_locker(self):
        # TODO: V8 had a process-wide global state that is removed in:
        # https://chromium-review.googlesource.com/c/v8/v8/+/3401595
        # But before we upgrade V8, we have to check this state.
        self.assertFalse(v8.Locker.is_active())
        with self.assertRaises(v8.JavaScriptError):
            with v8.Isolate() as isolate:
                self.call_target(isolate, contextlib.nullcontext())

        with v8.Isolate() as isolate:
            with v8.Locker(isolate) as locker:
                with self.assertRaisesRegex(
                    RuntimeError,
                    r'this locker is already locking an isolate',
                ):
                    locker.__enter__()

        # For now, our isolate wrapper class automatically acquires a
        # locker for its caller.
        self.assertTrue(v8.Locker.is_active())
        with v8.Isolate() as isolate:
            self.assertEqual(
                self.call_target(isolate, contextlib.nullcontext()),
                42,
            )

        with v8.Isolate() as isolate:
            self.assertEqual(
                self.call_target(isolate, v8.Locker(isolate)),
                42,
            )

    @staticmethod
    def call_target(isolate, locker):
        f = futures.Future()
        t = threading.Thread(
            target=futures.wrap_thread_target(target, f),
            args=(isolate, locker),
        )
        t.start()
        t.join()
        return f.get_result()


def target(isolate, locker):
    with \
        locker, \
        isolate.scope(), \
        v8.HandleScope(isolate), \
        v8.Context(isolate) as context \
    :
        v8.run(context, 'var x = 42;')
        return context['x']


if __name__ == '__main__':
    unittest.main()
