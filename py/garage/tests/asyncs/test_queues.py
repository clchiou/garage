import unittest

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

        self.assertListEqual([], await queue.close())
        self.assertTrue(queue.is_closed())

        with self.assertRaises(queues.Closed):
            await queue.put(4)

        self.assertEqual(1, await queue.get())
        self.assertEqual(2, await queue.get())
        self.assertEqual(3, await queue.get())

        with self.assertRaises(queues.Closed):
            await queue.get()


if __name__ == '__main__':
    unittest.main()
