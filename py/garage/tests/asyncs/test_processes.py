import unittest

import asyncio

from garage.asyncs.processes import process

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


if __name__ == '__main__':
    unittest.main()
