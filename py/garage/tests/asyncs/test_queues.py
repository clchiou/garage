import unittest

from tests.availability import curio_available

if curio_available:
    import curio
    from garage.asyncs import queues

from tests.asyncs.utils import synchronous


@unittest.skipUnless(curio_available, 'curio unavailable')
class QueueTest(unittest.TestCase):

    @synchronous
    async def test_queue(self):
        testdata = [
            (queues.Queue, [1, 2, 3], [1, 2, 3]),
        ]
        for queue_class, test_input, test_output in testdata:
            queue = queue_class(capacity=len(test_input))
            for data in test_input:
                queue.put_nowait(data)

            with self.assertRaises(queues.Full):
                queue.put_nowait(999)

            for data in test_output:
                self.assertEqual(data, queue.get_nowait())
            self.assertFalse(queue)

            with self.assertRaises(queues.Empty):
                queue.get_nowait()

    @synchronous
    async def test_close(self):
        queue = queues.Queue()
        await queue.put(1)
        await queue.put(2)
        await queue.put(3)

        self.assertListEqual([], queue.close())
        self.assertTrue(queue.is_closed())

        with self.assertRaises(queues.Closed):
            await queue.put(4)

        self.assertEqual(1, await queue.get())
        self.assertEqual(2, await queue.get())
        self.assertEqual(3, await queue.get())

        with self.assertRaises(queues.Closed):
            await queue.get()

    @synchronous
    async def test_raising_closed(self):

        num_expects = 4
        flag = curio.Event()
        queue = queues.Queue()

        async def expect_closed():
            nonlocal num_expects
            with self.assertRaises(queues.Closed):
                num_expects -= 1
                if num_expects == 0:
                    await flag.set()
                await queue.get()

        async def call_close():
            await flag.wait()
            queue.close()

        tasks = [await curio.spawn(call_close())]
        for _ in range(num_expects):
            tasks.append(await curio.spawn(expect_closed()))

        async for task in curio.wait(tasks):
            await task.join()

    @synchronous
    async def test_until_closed(self):

        queue = queues.Queue()
        with self.assertRaises(curio.TaskTimeout):
            async with curio.timeout_after(0.1):
                await queue.until_closed()

        queue.close()
        with self.assertRaises(queues.Closed):
            await queue.until_closed()


@unittest.skipUnless(curio_available, 'curio unavailable')
class ZeroQueueTest(unittest.TestCase):

    @synchronous
    async def test_put(self):
        zq = queues.ZeroQueue()
        with self.assertRaises(queues.Full):
            zq.put_nowait(42)
        zq.close()
        with self.assertRaises(queues.Closed):
            await zq.put(42)

    @synchronous
    async def test_get(self):
        zq = queues.ZeroQueue()
        with self.assertRaises(queues.Empty):
            zq.get_nowait()
        zq.close()
        with self.assertRaises(queues.Closed):
            await zq.get()


if __name__ == '__main__':
    unittest.main()
