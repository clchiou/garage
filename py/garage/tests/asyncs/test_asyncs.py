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


class TaskSetTest(unittest.TestCase):

    @synchronous
    async def test_graceful_exit(self):

        task_set = asyncs.TaskSet()

        async def waiter():
            results = set()
            async for task in task_set:
                results.add(await task.join())
            return results

        async def spawner():
            await task_set.spawn(func(1))
            await task_set.spawn(func(2))
            await task_set.spawn(func(3))

        async def func(x):
            return x

        waiter_task = await asyncs.spawn(waiter())
        async with task_set:
            spawner_task = await asyncs.spawn(spawner())
            await spawner_task.join()
            task_set.graceful_exit()
            await waiter_task.join()

        self.assertEqual({1, 2, 3}, await waiter_task.join())

    @synchronous
    async def test_abort(self):

        task_set = asyncs.TaskSet()
        tasks = []

        async def spawner():
            tasks.append(await task_set.spawn(func(1)))
            tasks.append(await task_set.spawn(func(2)))
            tasks.append(await task_set.spawn(func(3)))

        async def func(x):
            await curio.sleep(1)
            return x

        async with task_set:
            spawner_task = await asyncs.spawn(spawner())
            await spawner_task.join()

        self.assertEqual('CANCELLED', tasks[0].state)
        self.assertEqual('CANCELLED', tasks[1].state)
        self.assertEqual('CANCELLED', tasks[2].state)


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
