import unittest

import os
import select

from g1.asyncs.kernels import errors
from g1.asyncs.kernels import kernels
from g1.asyncs.kernels import pollers
from g1.asyncs.kernels import traps


class KernelTest(unittest.TestCase):

    def setUp(self):
        self.k = kernels.Kernel(sanity_check_frequency=1)
        r, w = os.pipe()
        os.set_blocking(r, False)
        os.set_blocking(w, False)
        self.r = os.fdopen(r, 'rb')
        self.w = os.fdopen(w, 'wb')

    def tearDown(self):
        self.k.close()
        self.r.close()
        self.w.close()

    def test_awaitable(self):

        class TestAwaitable:

            def __await__(self):
                yield traps.SleepTrap(traps.Traps.SLEEP, 0)

        async def do_test():
            await TestAwaitable()

        self.assert_stats(num_ticks=0)
        self.assertIsNone(self.k.run(do_test))
        self.assert_stats(num_ticks=1)
        self.assertIsNone(self.k.run(TestAwaitable()))
        self.assert_stats(num_ticks=2)

    def test_get_all_tasks(self):

        async def noop():
            pass

        async def block_forever():
            await traps.poll_read(self.r.fileno())

        async def do_sleep(duration):
            await traps.sleep(duration)

        self.assert_stats()

        t1 = self.k.spawn(noop)
        t2 = self.k.spawn(block_forever)
        t3 = self.k.spawn(do_sleep(100))
        t4 = self.k.spawn(do_sleep(None))

        actual = self.k.get_all_tasks()
        self.assert_stats(num_ticks=0, num_tasks=4, num_ready=4)
        self.assertEqual(set(actual), {t1, t2, t3, t4})

        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)

        actual = self.k.get_all_tasks()
        self.assert_stats(
            num_ticks=1, num_tasks=3, num_poll=1, num_sleep=1, num_blocked=1
        )
        self.assertEqual(set(actual), {t2, t3, t4})

        self.k.cancel(t2)
        self.k.cancel(t3)
        self.k.cancel(t4)
        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)

    def test_timeout(self):

        async def block_forever():
            await traps.poll_read(self.r.fileno())

        self.assert_stats()

        with self.assertRaises(errors.Timeout):
            self.k.run(block_forever, timeout=0)
        self.assert_stats(num_ticks=1, num_tasks=1, num_poll=1)

        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=2, num_tasks=1, num_poll=1)

        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=-1)
        self.assert_stats(num_ticks=3, num_tasks=1, num_poll=1)

        self.w.write(b'\x00')
        self.w.flush()
        self.k.run(timeout=1)
        self.assert_stats(num_ticks=5, num_tasks=0, num_poll=0)

    def test_timeout_after(self):

        task = None

        async def do_timeout_after():
            self.k.timeout_after(task, 99)
            await traps.poll_read(self.r.fileno())

        self.assert_stats()

        task = self.k.spawn(do_timeout_after)
        self.assert_stats(num_ticks=0, num_tasks=1, num_ready=1)

        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=1, num_tasks=1, num_poll=1, num_timeout=1)

        self.w.write(b'\x00')
        self.w.flush()
        self.k.run(timeout=1)
        self.assert_stats(num_ticks=3, num_tasks=0)

    def test_timeout_after_none(self):

        task = None

        async def do_timeout_after():
            self.k.timeout_after(task, None)
            await traps.poll_read(self.r.fileno())

        self.assert_stats()

        task = self.k.spawn(do_timeout_after)
        self.assert_stats(num_ticks=0, num_tasks=1, num_ready=1)

        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=1, num_tasks=1, num_poll=1, num_timeout=0)

        self.w.write(b'\x00')
        self.w.flush()
        self.k.run(timeout=1)
        self.assert_stats(num_ticks=3, num_tasks=0)

    def test_join(self):

        async def compute(x):
            return x * x

        async def aggregate(ts):
            total = 0
            for t in ts:
                total += await t.get_result()
            return total

        self.assert_stats()
        ts = [self.k.spawn(compute(x)) for x in [1, 2, 3, 4]]
        self.assert_stats(num_tasks=4, num_ready=4)
        self.assertEqual(self.k.run(aggregate(ts)), 1 + 4 + 9 + 16)
        self.assert_stats(num_ticks=1)

    def test_join_self(self):

        task = None

        async def join_self():
            await task.join()

        task = self.k.spawn(join_self)
        self.k.run()
        self.assertTrue(task.is_completed())
        pattern = r'expect non-'
        with self.assertRaisesRegex(AssertionError, pattern):
            task.get_result_nonblocking()

    def test_cancel(self):

        n = self.k._nudger._r
        self.assertEqual(self.k._poller._fds, set([n]))

        self.assert_stats()

        task = self.k.spawn(traps.poll_read(self.r.fileno()))
        self.assert_stats(num_ticks=0, num_tasks=1, num_ready=1)

        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)
        self.assertEqual(self.k._poller._fds, set([n, self.r.fileno()]))
        self.assert_stats(num_ticks=1, num_tasks=1, num_poll=1)

        self.k.cancel(task)
        self.assert_stats(
            num_ticks=1, num_tasks=1, num_ready=1, num_to_raise=1
        )

        self.k.run()
        self.assert_stats(num_ticks=2, num_tasks=0)

        self.assertEqual(self.k._poller._fds, set([n]))

        with self.assertRaises(errors.Cancelled):
            task.get_result_nonblocking()

    def test_poll(self):

        self.assert_stats()

        with self.assertRaises(errors.Timeout):
            self.k.run(traps.poll_read(self.r.fileno()), timeout=0)
        self.assert_stats(num_ticks=1, num_tasks=1, num_poll=1)

        self.w.write(b'\x00')
        self.w.flush()

        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=2, num_tasks=1, num_ready=1)

        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=3, num_tasks=0, num_poll=0)

    def test_block(self):

        source = object()
        task = self.k.spawn(traps.block(source))
        self.assert_stats(num_ticks=0, num_tasks=1, num_ready=1)
        self.assertFalse(task.is_completed())

        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=1, num_tasks=1, num_blocked=1)
        self.assertFalse(task.is_completed())

        self.k.unblock(source)
        self.k.run()
        self.assert_stats(num_ticks=2, num_tasks=0, num_blocked=0)
        self.assertTrue(task.is_completed())

    def test_post_block_callback(self):

        source = object()

        task = self.k.spawn(
            traps.block(source, lambda: self.k.unblock(source))
        )
        self.assert_stats(num_ticks=0, num_tasks=1, num_ready=1)
        self.assertFalse(task.is_completed())

        self.k.run()
        self.assert_stats(num_ticks=1, num_tasks=0, num_blocked=0)
        self.assertTrue(task.is_completed())

    def test_cleanup_tasks_on_close(self):

        async def block_forever():
            await traps.sleep(None)

        async def reraise():
            try:
                await traps.sleep(None)
            except GeneratorExit:
                raise ValueError('some error')

        async def noop():
            pass

        t1 = self.k.spawn(block_forever)
        t2 = self.k.spawn(reraise)
        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)

        t3 = self.k.spawn(noop)

        self.k.close()

        self.assertEqual(set(self.k.get_all_tasks()), {t1, t2, t3})
        for t in (t1, t2, t3):
            self.assertTrue(t.is_completed())
        with self.assertRaisesRegex(errors.Cancelled, r'task abort'):
            t1.get_result_nonblocking()
        with self.assertRaisesRegex(ValueError, r'some error'):
            t2.get_result_nonblocking()
        with self.assertRaisesRegex(errors.Cancelled, r'task abort'):
            t3.get_result_nonblocking()

        # It is okay to call ``abort`` repeatedly.
        t1.abort()
        t1.abort()
        t1.abort()

    def test_close_repeatedly(self):
        self.k.close()
        self.k.close()
        self.k.close()

    def assert_stats(self, **expect):
        actual = self.k.get_stats()._asdict()
        # Default ``expect`` entries to 0.
        for name in actual:
            if name not in expect:
                expect[name] = 0
        self.assertEqual(actual, expect)


class NudgerTest(unittest.TestCase):

    def test_nudge(self):
        nudger = kernels.Nudger()

        try:
            os.write(nudger._w, b'\x00' * 65535)
        except BlockingIOError:
            pass

        # ``nudge`` should swallow ``BlockingIOError``.
        for _ in range(8):
            nudger.nudge()

        with self.assertRaises(BlockingIOError):
            os.write(nudger._w, b'\x00')

        nudger.close()

    def test_poller(self):
        poller = pollers.Epoll()
        nudger = kernels.Nudger()
        nudger.register_to(poller)

        self.assertEqual(poller.poll(0), [])

        nudger.nudge()
        self.assertEqual(poller.poll(0), [(nudger._r, select.EPOLLIN)])

        nudger.ack()
        self.assertEqual(poller.poll(0), [])

        poller.close()
        nudger.close()


if __name__ == '__main__':
    unittest.main()
