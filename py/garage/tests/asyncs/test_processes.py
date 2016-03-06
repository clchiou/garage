import unittest

import asyncio

from garage.asyncs.processes import process
from garage.asyncs.utils import synchronous


class MyException(Exception):
    pass


@process
async def raises(exit):
    raise MyException


@process
async def until_exit(exit):
    await exit


class ProcessesTest(unittest.TestCase):

    @synchronous
    async def test_stop(self):
        proc = until_exit()
        self.assertFalse(proc.done())
        proc.stop()
        await proc
        self.assertTrue(proc.done())

    @synchronous
    async def test_raises(self):
        proc = raises()
        self.assertFalse(proc.done())
        with self.assertRaises(MyException):
            await proc
        self.assertTrue(proc.done())


if __name__ == '__main__':
    unittest.main()
