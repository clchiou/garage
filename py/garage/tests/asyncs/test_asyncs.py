import unittest

import signal

import curio

from garage import asyncs

from tests.asyncs.utils import synchronous


class SpawnTest(unittest.TestCase):

    @synchronous
    async def test_spawn(self):

        async def coro():
            try:
                await curio.sleep(100)
            except Exception as e:
                self.fail('asyncs.TaskCancelled is not raised: %r' % e)

        task = await asyncs.spawn(coro())
        self.assertTrue(await task.cancel())
        with self.assertRaises(curio.TaskError):
            await task.join()
        self.assertEqual('CANCELLED', task.state)

    @synchronous
    async def test_wrapper(self):

        async def coro():
            async with curio.SignalSet(signal.SIGINT) as sigset:
                await sigset.wait()
                self.fail('asyncs.TaskCancelled is not raised: %r' % e)

        task = await asyncs.spawn(coro())
        self.assertTrue(await task.cancel())
        with self.assertRaises(curio.TaskError):
            await task.join()
        self.assertEqual('CANCELLED', task.state)


class TaskStackTest(unittest.TestCase):

    @synchronous
    async def test_task_stack(self):

        results = []

        async def func(data):
            try:
                await curio.sleep(10)
            finally:
                results.append(data)

        async with asyncs.TaskStack() as stack:
            await stack.spawn(func(1))
            await stack.spawn(func(2))

        self.assertEqual([2, 1], results)


if __name__ == '__main__':
    unittest.main()
