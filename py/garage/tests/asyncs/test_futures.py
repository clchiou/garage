import unittest

import curio

from garage.asyncs.futures import CancelledError, Future, State
from garage.asyncs.utils import synchronous


class FuturesTest(unittest.TestCase):

    @synchronous
    async def test_result(self):

        f = Future()
        p = f.make_promise()
        self.assertFalse(p.is_cancelled())
        self.assertIs(f.state, State.PENDING)

        await p.set_result(1)

        self.assertIs(f.state, State.FINISHED)
        self.assertEqual(1, await f.get_result())
        self.assertIsNone(await f.get_exception())

        with self.assertRaisesRegex(AssertionError, 'marked FINISHED'):
            await p.set_result(1)

    @synchronous
    async def test_exception(self):

        f = Future()
        p = f.make_promise()

        exc = ValueError('test exception')
        await p.set_exception(exc)

        with self.assertRaisesRegex(ValueError, 'test exception'):
            await f.get_result()
        self.assertEqual(exc, await f.get_exception())

    @synchronous
    async def test_cancel(self):

        f = Future()
        p = f.make_promise()

        await f.cancel()

        # Since Future is cancelled, calls to Promise are ignored.
        await p.set_result(99)
        await p.set_exception(ValueError())

        with self.assertRaises(CancelledError):
            await f.get_result()
        with self.assertRaises(CancelledError):
            await f.get_exception()


if __name__ == '__main__':
    unittest.main()
