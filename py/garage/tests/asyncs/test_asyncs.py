import unittest

from tests.availability import curio_available

import signal

if curio_available:
    import curio
    from garage import asyncs
    from garage.asyncs.utils import synchronous


@unittest.skipUnless(curio_available, 'curio unavailable')
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
        self.assertTrue(task.cancelled)
        self.assertTrue(task.terminated)

    @synchronous
    async def test_wrapper(self):

        async def coro():
            await curio.Event().wait()
            self.fail('asyncs.TaskCancelled is not raised: %r' % e)

        task = await asyncs.spawn(coro())
        self.assertTrue(await task.cancel())
        with self.assertRaises(curio.TaskError):
            await task.join()
        self.assertTrue(task.cancelled)
        self.assertTrue(task.terminated)


@unittest.skipUnless(curio_available, 'curio unavailable')
class TaskSetTest(unittest.TestCase):

    @synchronous
    async def test_ignore_done_tasks(self):

        task_set = asyncs.TaskSet()
        task_set.ignore_done_tasks()

        async def func():
            pass

        async with task_set:

            t1 = await task_set.spawn(func())
            t2 = await task_set.spawn(func())
            t3 = await task_set.spawn(func())

            await t1.join()
            await t2.join()
            await t3.join()

            # We should not have "done tasks".
            self.assertIsNone(await task_set.next_done())

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

        for task in tasks:
            self.assertTrue(task.cancelled)
            self.assertTrue(task.terminated)


@unittest.skipUnless(curio_available, 'curio unavailable')
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


@unittest.skipUnless(curio_available, 'curio unavailable')
class SelectTest(unittest.TestCase):

    @synchronous
    async def test_select(self):

        async def f(x):
            return x

        task_1 = await asyncs.spawn(f('x'))
        task_2 = await asyncs.spawn(f('x'))
        task = await asyncs.select([task_1, task_2])
        self.assertIn(task, [task_1, task_2])
        self.assertTrue(task.terminated)
        self.assertEqual('x', await task.join())

        task_3 = await asyncs.spawn(f('p'))
        task_4 = await asyncs.spawn(f('q'))
        task, label = await asyncs.select({task_3: 'p', task_4: 'q'})
        self.assertIn(task, [task_3, task_4])
        self.assertTrue(task.terminated)
        self.assertEqual(label, await task.join())

        task = await asyncs.select([f('x'), f('x')])
        self.assertTrue(task.terminated)
        self.assertEqual('x', await task.join())

        task, label = await asyncs.select({f('p'): 'p', f('q'): 'q'})
        self.assertTrue(task.terminated)
        self.assertEqual(label, await task.join())


@unittest.skipUnless(curio_available, 'curio unavailable')
class AsyncsTest(unittest.TestCase):

    @synchronous
    async def test_socket_close(self):

        e1 = asyncs.Event()
        e2 = asyncs.Event()

        async def use_socket(socket, event):
            with self.assertRaisesRegex(OSError, r'Bad file descriptor'):
                event.set()
                await socket.recv(32)

        s1, s2 = curio.socket.socketpair()
        f1 = s1._fileno
        f2 = s2._fileno

        task1 = await asyncs.spawn(use_socket(s1, e1))
        task2 = await asyncs.spawn(use_socket(s2, e2))

        try:
            async with curio.timeout_after(1):

                await e1.wait()
                await e2.wait()

                kernel = await curio.traps._get_kernel()

                self.assertIsNotNone(kernel._selector.get_key(f1))
                self.assertIsNotNone(kernel._selector.get_key(f2))

                await asyncs.close_socket_and_wakeup_task(s1)
                await asyncs.close_socket_and_wakeup_task(s2)

                with self.assertRaises(KeyError):
                    kernel._selector.get_key(f1)
                with self.assertRaises(KeyError):
                    kernel._selector.get_key(f2)

                await task1.join()
                await task2.join()

        finally:
            await task1.cancel()
            await task2.cancel()
            await s1.close()
            await s2.close()


if __name__ == '__main__':
    unittest.main()
