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
                self.call(return_42, isolate, contextlib.nullcontext())

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
                self.call(return_42, isolate, contextlib.nullcontext()),
                42,
            )

        with v8.Isolate() as isolate:
            self.assertEqual(
                self.call(return_42, isolate, v8.Locker(isolate)),
                42,
            )

        # Test global context.
        with contextlib.ExitStack() as exit_stack:
            isolate = exit_stack.enter_context(v8.Isolate())
            with \
                v8.Locker(isolate), \
                isolate.scope(), \
                v8.HandleScope(isolate) \
            :
                with v8.Context(isolate) as c1:
                    c1['x'] = 42
                    g1 = exit_stack.enter_context(
                        v8.GlobalContext(isolate, c1)
                    )
                with v8.Context(isolate) as c2:
                    c2['x'] = 99
                    g2 = exit_stack.enter_context(
                        v8.GlobalContext(isolate, c2)
                    )

            self.assertEqual(self.call(global_context_get, isolate, g1), 42)
            self.assertEqual(self.call(global_context_get, isolate, g2), 99)
            self.call(global_context_set, isolate, g1, 43)
            self.assertEqual(self.call(global_context_get, isolate, g1), 43)
            self.assertEqual(self.call(global_context_get, isolate, g2), 99)

    @staticmethod
    def call(target, *args):
        f = futures.Future()
        t = threading.Thread(
            target=futures.wrap_thread_target(target, f),
            args=args,
        )
        t.start()
        t.join()
        return f.get_result()


def return_42(isolate, locker):
    with \
        locker, \
        isolate.scope(), \
        v8.HandleScope(isolate), \
        v8.Context(isolate) as context \
    :
        v8.run(context, 'var x = 42;')
        return context['x']


def global_context_get(isolate, global_context):
    with \
        v8.Locker(isolate), \
        isolate.scope(), \
        v8.HandleScope(isolate) \
    :
        return global_context.get(isolate)['x']


def global_context_set(isolate, global_context, new_x):
    with \
        v8.Locker(isolate), \
        isolate.scope(), \
        v8.HandleScope(isolate) \
    :
        global_context.get(isolate)['x'] = new_x


if __name__ == '__main__':
    unittest.main()
