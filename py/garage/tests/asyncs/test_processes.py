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


if __name__ == '__main__':
    unittest.main()
