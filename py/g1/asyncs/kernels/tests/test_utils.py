import unittest

from g1.asyncs.kernels import contexts
from g1.asyncs.kernels import errors
from g1.asyncs.kernels import kernels
from g1.asyncs.kernels import locks
from g1.asyncs.kernels import utils


async def square(x):
    return x * x


async def raises(message):
    raise Exception(message)


class TaskCompletionQueueTest(unittest.TestCase):

    def setUp(self):
        self.k = kernels.Kernel()
        self.token = contexts.set_kernel(self.k)

    def tearDown(self):
        contexts.KERNEL.reset(self.token)
        self.k.close()

    def test_queue(self):

        tq = utils.TaskCompletionQueue()
        self.assertFalse(tq.is_closed())
        self.assertFalse(tq)
        self.assertEqual(len(tq), 0)

        t1 = self.k.spawn(square(1))
        tq.put(t1)
        self.assertFalse(tq.is_closed())
        self.assertTrue(tq)
        self.assertEqual(len(tq), 1)

        t2 = self.k.spawn(square(1))
        tq.put(t2)
        self.assertFalse(tq.is_closed())
        self.assertTrue(tq)
        self.assertEqual(len(tq), 2)

        tq.close()
        self.assertTrue(tq.is_closed())
        self.assertTrue(tq)
        self.assertEqual(len(tq), 2)

        with self.assertRaises(utils.Closed):
            tq.put(None)

        ts = set()

        ts.add(self.k.run(tq.get, timeout=1))
        self.assertTrue(tq.is_closed())
        self.assertTrue(tq)
        self.assertEqual(len(tq), 1)

        ts.add(self.k.run(tq.get, timeout=1))
        self.assertTrue(tq.is_closed())
        self.assertFalse(tq)
        self.assertEqual(len(tq), 0)

        with self.assertRaises(utils.Closed):
            self.k.run(tq.get)

        self.assertEqual(ts, {t1, t2})

    def test_context_manager(self):
        tq = utils.TaskCompletionQueue()

        t1 = self.k.spawn(square(1))
        tq.put(t1)

        t2 = self.k.spawn(square(2))
        tq.put(t2)

        async def do_with_queue():
            async with tq:
                return 42

        self.assertEqual(self.k.run(do_with_queue, timeout=1), 42)

        self.assertTrue(tq.is_closed())
        self.assertFalse(tq)
        self.assertEqual(len(tq), 0)

        for t, x in [(t1, 1), (t2, 2)]:
            self.assertTrue(t.is_completed())
            self.assertEqual(t.get_result_nonblocking(), x * x)

    def test_context_manager_cancel(self):
        tq = utils.TaskCompletionQueue()

        event = locks.Event()

        t1 = self.k.spawn(event.wait)
        tq.put(t1)

        t2 = self.k.spawn(event.wait)
        tq.put(t2)

        t3 = self.k.spawn(raises('test message'))
        tq.put(t3)

        async def do_with_queue():
            async with tq:
                raise Exception('some error')

        with self.assertRaisesRegex(Exception, r'some error'):
            self.k.run(do_with_queue)

        self.assertTrue(tq.is_closed())
        self.assertFalse(tq)
        self.assertEqual(len(tq), 0)

        for t in (t1, t2):
            self.assertTrue(t.is_completed())
            with self.assertRaises(errors.Cancelled):
                t.get_result_nonblocking()

        self.assertTrue(t3.is_completed())
        with self.assertRaisesRegex(Exception, r'test message'):
            t3.get_result_nonblocking()


if __name__ == '__main__':
    unittest.main()
