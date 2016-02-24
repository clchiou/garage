import unittest

import asyncio

from garage.asyncs.processes import ensure_process

from . import synchronous


class MyException(Exception):
    pass


@ensure_process
async def recv_messages(inbox, flag, messages):
    await flag.wait()
    while True:
        messages.append(await inbox.get())


@ensure_process
async def raises(inbox):
    raise MyException


class ProcessesTest(unittest.TestCase):

    @synchronous
    async def test_process(self):
        flag = asyncio.Event()
        messages = []
        proc = recv_messages(flag, messages)
        await proc.send(1)
        await proc.send(2)
        await proc.send(3)
        await proc.shutdown()
        self.assertListEqual([], messages)
        flag.set()
        await proc
        self.assertTrue(proc.task.done())
        self.assertListEqual([1, 2, 3], messages)

    @synchronous
    async def test_link(self):
        flag1 = asyncio.Event()
        msgs1 = []
        proc1 = recv_messages(flag1, msgs1)
        flag2 = asyncio.Event()
        msgs2 = []
        proc2 = recv_messages(flag2, msgs2)
        flag3 = asyncio.Event()
        msgs3 = []
        proc3 = recv_messages(flag3, msgs3)

        proc1.link(proc2)
        proc2.link(proc3)

        await proc1.send(1)
        await proc2.send(2)
        await proc3.send(3)

        await proc3.shutdown()
        self.assertListEqual([], msgs1)
        self.assertListEqual([], msgs2)
        self.assertListEqual([], msgs3)
        self.assertFalse(proc1.inbox.is_closed())
        self.assertFalse(proc2.inbox.is_closed())
        self.assertTrue(proc3.inbox.is_closed())

        flag3.set()
        await proc3

        flag2.set()
        await proc2

        flag1.set()
        await proc1

        self.assertTrue(proc1.task.done())
        self.assertTrue(proc2.task.done())
        self.assertTrue(proc3.task.done())

        # proc1 and proc2 was shut down non-gracefully.
        self.assertListEqual([], msgs1)
        self.assertListEqual([], msgs2)
        self.assertListEqual([3], msgs3)

    @synchronous
    async def test_shutdown_recursively(self):
        flag = asyncio.Event()
        msgs1 = []
        proc1 = recv_messages(flag, msgs1)
        msgs2 = []
        proc2 = recv_messages(flag, msgs2)
        msgs3 = []
        proc3 = recv_messages(flag, msgs3)

        proc1.link(proc2)
        proc2.link(proc3)

        await proc1.send(1)
        await proc2.send(2)
        await proc3.send(3)

        await proc3.shutdown(recursive=True)
        self.assertListEqual([], msgs1)
        self.assertListEqual([], msgs2)
        self.assertListEqual([], msgs3)
        self.assertTrue(proc1.inbox.is_closed())
        self.assertTrue(proc2.inbox.is_closed())
        self.assertTrue(proc3.inbox.is_closed())

        flag.set()
        await proc1
        await proc2
        await proc3

        self.assertTrue(proc1.task.done())
        self.assertTrue(proc2.task.done())
        self.assertTrue(proc3.task.done())

        self.assertListEqual([1], msgs1)
        self.assertListEqual([2], msgs2)
        self.assertListEqual([3], msgs3)

    @synchronous
    async def test_raises(self):
        proc = raises()
        with self.assertRaises(MyException):
            await proc


if __name__ == '__main__':
    unittest.main()
