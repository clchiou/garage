import unittest

import asyncio

from garage.asyncs import queues

from . import synchronous


class QueueTest(unittest.TestCase):

    @synchronous
    async def test_queue(self):
        testdata = [
            (queues.Queue, [1, 2, 3], [1, 2, 3]),
        ]
        for queue_class, test_input, test_output in testdata:
            queue = queue_class(capacity=len(test_input))
            for data in test_input:
                await queue.put(data, block=False)

            with self.assertRaises(queues.Full):
                await queue.put(999, block=False)

            for data in test_output:
                self.assertEqual(data, await queue.get(block=False))
            self.assertFalse(queue)

            with self.assertRaises(queues.Empty):
                await queue.get(block=False)

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
        flag = asyncio.Event()
        queue = queues.Queue()

        async def expect_closed():
            nonlocal num_expects
            with self.assertRaises(queues.Closed):
                num_expects -= 1
                if num_expects == 0:
                    flag.set()
                await queue.get()

        async def call_close():
            await flag.wait()
            queue.close()

        fs = [asyncio.ensure_future(call_close())]
        for _ in range(num_expects):
            fs.append(asyncio.ensure_future(expect_closed()))

        for fut in asyncio.as_completed(fs):
            await fut


if __name__ == '__main__':
    unittest.main()
