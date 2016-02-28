import unittest

import asyncio

from garage.asyncs.processes import (
    each_completed,
    each_of,
    one_completed,
    one_of,
    process,
)

from . import synchronous


class MyException(Exception):
    pass


@process
async def recv_messages(inbox, flag, messages):
    await flag.wait()
    while True:
        messages.append(await inbox.get())


@process
async def raises(inbox):
    raise MyException


@process
async def until_closed(inbox):
    await inbox.until_closed()


class ProcessesTest(unittest.TestCase):

    @synchronous
    async def test_process(self):
        flag = asyncio.Event()
        messages = []
        proc = recv_messages(flag, messages)
        await proc.inbox.put(1)
        await proc.inbox.put(2)
        await proc.inbox.put(3)
        proc.inbox.close()
        self.assertListEqual([], messages)
        flag.set()
        await proc.task
        self.assertTrue(proc.task.done())
        self.assertListEqual([1, 2, 3], messages)

    @synchronous
    async def test_raises(self):
        proc = raises()
        with self.assertRaises(MyException):
            await proc.task

    @synchronous
    async def test_context(self):
        for make_proc in [until_closed, raises]:
            # Let context manager do await.
            async with make_proc() as proc:
                pass
            self.assertTrue(proc.task.done())
            # Context manager won't (?) do await.
            async with make_proc() as proc:
                await asyncio.sleep(0.01)
            self.assertTrue(proc.task.done())


class WaitHelpersTest(unittest.TestCase):

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
