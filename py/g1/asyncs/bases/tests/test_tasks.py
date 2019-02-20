import unittest

from g1.asyncs.bases import locks
from g1.asyncs.bases import tasks
from g1.asyncs.kernels import contexts
from g1.asyncs.kernels import errors
from g1.asyncs.kernels import kernels
from g1.asyncs.kernels.tasks import Task


async def square(x):
    return x * x


async def raises(message):
    raise Exception(message)


class CompletionQueueTest(unittest.TestCase):

    def setUp(self):
        self.k = kernels.Kernel()
        self.token = contexts.set_kernel(self.k)

    def tearDown(self):
        contexts.KERNEL.reset(self.token)
        self.k.close()

    def test_queue(self):

        tq = tasks.CompletionQueue()
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

        with self.assertRaises(tasks.Closed):
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

        with self.assertRaises(tasks.Closed):
            self.k.run(tq.get)

        self.assertEqual(ts, {t1, t2})

    def test_close_repeatedly(self):
        tq = tasks.CompletionQueue()
        self.assertFalse(tq.is_closed())

        t1 = self.k.spawn(square(1))
        tq.put(t1)

        self.assertEqual(tq.close(True), [])
        self.assertTrue(tq.is_closed())
        self.assertEqual(tq.close(False), [t1])
        self.assertTrue(tq.is_closed())
        self.assertEqual(tq.close(True), [])
        self.assertTrue(tq.is_closed())
        self.assertEqual(tq.close(False), [])
        self.assertTrue(tq.is_closed())

        self.assertFalse(t1.is_completed())
        self.k.run(timeout=1)
        self.assertTrue(t1.is_completed())

    def test_async_iterator(self):
        tq = tasks.CompletionQueue()

        expect = {
            tq.spawn(square(1)),
            tq.spawn(square(2)),
            tq.spawn(square(3)),
        }
        tq.close()

        async def async_iter():
            actual = set()
            async for task in tq:
                actual.add(task)
            return actual

        self.assertEqual(
            self.k.run(async_iter, timeout=1),
            expect,
        )

    def test_not_wait_for(self):
        tq = tasks.CompletionQueue()
        event = locks.Event()

        t1 = self.k.spawn(event.wait)
        tq.put(t1, wait_for_completion=False)

        t2 = self.k.spawn(event.wait)
        tq.put(t2, wait_for_completion=False)

        tq.close()
        self.assertTrue(tq.is_closed())
        self.assertTrue(tq)
        self.assertEqual(len(tq), 2)

        self.assertFalse(tq._completed)
        self.assertFalse(tq._uncompleted)
        self.assertEqual(tq._not_wait_for, {t1, t2})
        with self.assertRaises(tasks.Closed):
            self.k.run(tq.get, timeout=0)
        self.assertFalse(tq._completed)
        self.assertFalse(tq._uncompleted)
        self.assertEqual(tq._not_wait_for, {t1, t2})

        event.set()
        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assertEqual(set(tq._completed), {t1, t2})
        self.assertFalse(tq._uncompleted)
        self.assertFalse(tq._not_wait_for)

        ts = set()
        for n in (1, 0):
            ts.add(self.k.run(tq.get, timeout=1))
            self.assertTrue(tq.is_closed())
            self.assertEqual(bool(tq), n != 0)
            self.assertEqual(len(tq), n)
        self.assertFalse(tq)

        with self.assertRaises(tasks.Closed):
            self.k.run(tq.get)

        self.assertEqual(ts, {t1, t2})

    def test_spawn(self):
        tq = tasks.CompletionQueue()
        tq.close()
        self.assertEqual(self.k.get_all_tasks(), [])
        with self.assertRaises(tasks.Closed):
            tq.spawn(square)
        self.assertEqual(self.k.get_all_tasks(), [])

    def test_context_manager(self):
        tq = tasks.CompletionQueue()

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
        tq = tasks.CompletionQueue()

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


class CompletionQueueWithoutKernelTest(unittest.TestCase):

    def test_queue(self):
        with self.assertRaises(LookupError):
            contexts.get_kernel()

        tq = tasks.CompletionQueue()
        self.assertFalse(tq.is_closed())
        self.assertFalse(tq)
        self.assertEqual(len(tq), 0)

        task = Task(square(7))
        tq.put(task)
        self.assertFalse(tq.is_closed())
        self.assertTrue(tq)
        self.assertEqual(len(tq), 1)

        tq.close()
        self.assertTrue(tq.is_closed())
        self.assertTrue(tq)
        self.assertEqual(len(tq), 1)

        self.assertIsNone(task.tick(None, None))


class AsCompletedTest(unittest.TestCase):

    def setUp(self):
        self.k = kernels.Kernel()
        self.token = contexts.set_kernel(self.k)

    def tearDown(self):
        contexts.KERNEL.reset(self.token)
        self.k.close()

    def test_as_completed(self):

        async def test(ts):
            xs = set()
            async for t in tasks.as_completed(ts):
                xs.add(t.get_result_nonblocking())
            return xs

        self.assertEqual(self.k.run(test([])), set())

        ts = [self.k.spawn(square(x)) for x in (1, 2, 3)]
        self.assertEqual(self.k.run(test(ts)), {1, 4, 9})


class JoiningTest(unittest.TestCase):

    def setUp(self):
        self.k = kernels.Kernel()
        self.token = contexts.set_kernel(self.k)

    def tearDown(self):
        contexts.KERNEL.reset(self.token)
        self.k.close()

    def test_joining(self):

        async def test_normal(t1):
            async with tasks.joining(t1) as t2:
                self.assertIs(t1, t2)

        async def test_error(t1):
            async with tasks.joining(t1) as t2:
                self.assertIs(t1, t2)
                raise Exception('some error')

        t = self.k.spawn(square(2))
        self.k.run(test_normal(t))
        self.assertTrue(t.is_completed())
        self.assertEqual(t.get_result_nonblocking(), 4)

        t = self.k.spawn(locks.Event().wait)
        with self.assertRaisesRegex(Exception, r'some error'):
            self.k.run(test_error(t))
        self.assertTrue(t.is_completed())
        with self.assertRaises(errors.Cancelled):
            t.get_result_nonblocking()


class GetTaskTest(unittest.TestCase):

    def test_get_task(self):

        async def func():
            return tasks.get_current_task()

        self.assertEqual(tasks.get_all_tasks(), [])
        self.assertIsNone(tasks.get_current_task())

        k = kernels.Kernel()
        token = contexts.set_kernel(k)
        try:
            task = k.spawn(func)
            self.assertEqual(tasks.get_all_tasks(), [task])

            k.run(timeout=1)
            self.assertEqual(tasks.get_all_tasks(), [])

            self.assertIs(task, task.get_result_nonblocking())

        finally:
            contexts.KERNEL.reset(token)
            k.close()

        self.assertEqual(tasks.get_all_tasks(), [])
        self.assertIsNone(tasks.get_current_task())


if __name__ == '__main__':
    unittest.main()
