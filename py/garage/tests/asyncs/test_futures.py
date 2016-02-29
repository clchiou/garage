import unittest

import asyncio

from garage.asyncs.futures import (
    awaiting,
    each_completed,
    each_of,
    one_completed,
    one_of,
)

from . import synchronous


class FuturesTest(unittest.TestCase):

    @synchronous
    async def test_awaiting(self):
        async with awaiting(do_nothing()) as fut:
            pass
        self.assertTrue(fut.done())

        data = []
        async with awaiting.callback(lambda: data.append(42)):
            self.assertListEqual([], data)
        self.assertListEqual([42], data)

        async with awaiting.replaceable(cancel_on_exit=True) as box:
            self.assertIsNone(await box.remove())

            f1 = asyncio.ensure_future(asyncio.sleep(100))
            self.assertIs(f1, box.set(f1))

            self.assertFalse(f1.done())
            self.assertIs(f1, await box.remove())
            self.assertTrue(f1.done())
            self.assertTrue(f1.cancelled())

            f2 = asyncio.ensure_future(asyncio.sleep(100))
            self.assertIs(f2, box.set(f2))

            self.assertFalse(f2.done())

        self.assertTrue(f2.done())
        self.assertTrue(f2.cancelled())

    @synchronous
    async def test_each_completed(self):
        f1 = asyncio.ensure_future(do_nothing())
        f2 = asyncio.ensure_future(asyncio.sleep(100))
        async for fut in each_completed([f1], [f2]):
            self.assertIs(f1, fut)
            self.assertTrue(fut.done())
            self.assertEqual(42, await fut)
        self.assertFalse(f2.done())
        f2.cancel()

        f1 = asyncio.ensure_future(do_nothing())
        f2 = asyncio.ensure_future(asyncio.sleep(100))
        async for value in each_of([f1], [f2]):
            self.assertTrue(f1.done())
            self.assertEqual(42, value)
        self.assertFalse(f2.done())
        f2.cancel()

        f1 = asyncio.ensure_future(asyncio.sleep(100))
        f2 = asyncio.ensure_future(asyncio.sleep(100))
        with self.assertRaises(asyncio.TimeoutError):
            async for fut in each_completed([f1], [f2], timeout=0.01):
                self.fail(repr(fut))
        with self.assertRaises(asyncio.CancelledError):
            await f1
        self.assertTrue(f1.done())
        self.assertFalse(f2.done())
        f2.cancel()

    @synchronous
    async def test_one_completed(self):
        f1 = asyncio.ensure_future(do_nothing())
        f2 = asyncio.ensure_future(asyncio.sleep(100))
        f3 = asyncio.ensure_future(asyncio.sleep(100))
        fut = await one_completed([f1, f2], [f3])
        self.assertIs(f1, fut)
        self.assertTrue(fut.done())
        self.assertEqual(42, await fut)
        with self.assertRaises(asyncio.CancelledError):
            await f2
        self.assertFalse(f3.done())
        f3.cancel()

        f1 = asyncio.ensure_future(do_nothing())
        f2 = asyncio.ensure_future(asyncio.sleep(100))
        f3 = asyncio.ensure_future(asyncio.sleep(100))
        value = await one_of([f1, f2], [f3])
        self.assertTrue(f1.done())
        self.assertEqual(42, value)
        with self.assertRaises(asyncio.CancelledError):
            await f2
        self.assertFalse(f3.done())
        f3.cancel()

        f1 = asyncio.ensure_future(asyncio.sleep(100))
        f2 = asyncio.ensure_future(asyncio.sleep(100))
        with self.assertRaises(asyncio.TimeoutError):
            fut = await one_completed([f1], [f2], timeout=0.01)
            self.fail(repr(fut))
        with self.assertRaises(asyncio.CancelledError):
            await f1
        self.assertTrue(f1.done())
        self.assertFalse(f2.done())
        f2.cancel()


async def do_nothing():
    return 42


if __name__ == '__main__':
    unittest.main()
