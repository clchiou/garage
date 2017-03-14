import unittest

import curio

from garage.asyncs.futures import CancelledError, Future, State

from tests.asyncs.utils import synchronous


class FuturesTest(unittest.TestCase):

    @synchronous
    async def test_result(self):

        f = Future()
        p = f.make_promise()
        self.assertFalse(p.is_cancelled())
        self.assertIs(f.state, State.PENDING)

        p.set_result(1)

        self.assertIs(f.state, State.FINISHED)
        self.assertEqual(1, await f.get_result())
        self.assertIsNone(await f.get_exception())

        with self.assertRaisesRegex(AssertionError, 'marked FINISHED'):
            p.set_result(1)

    @synchronous
    async def test_exception(self):

        f = Future()
        p = f.make_promise()

        exc = ValueError('test exception')
        p.set_exception(exc)

        # Note: we can't use assertRaises here because for some reason
        # it clears stack frame of the task, and that will cause CPython
        # to raise a RuntimeError with message:
        #   cannot reuse already awaited coroutine
        # See Objects/genobject.c for more details.
        try:
            await f.get_result()
            self.fail('get_result() did not raise')
        except ValueError as e:
            self.assertEqual(exc, e)
        self.assertEqual(exc, await f.get_exception())

    @synchronous
    async def test_cancel(self):

        f = Future()
        p = f.make_promise()

        f.cancel()

        # Since Future is cancelled, calls to Promise are ignored.
        p.set_result(99)
        p.set_exception(ValueError())

        with self.assertRaises(CancelledError):
            await f.get_result()
        with self.assertRaises(CancelledError):
            await f.get_exception()


if __name__ == '__main__':
    unittest.main()
