import unittest

import contextlib
import os

from g1.asyncs.kernels import errors
from g1.asyncs.kernels import kernels
from g1.asyncs.kernels import pollers
from g1.asyncs.kernels import traps


class KernelTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.exit_stack = contextlib.ExitStack()

        self.k = kernels.Kernel(sanity_check_frequency=1)
        self.exit_stack.callback(self.k.close)

        r, w = os.pipe()
        os.set_blocking(r, False)
        os.set_blocking(w, False)
        self.r = os.fdopen(r, 'rb')
        self.w = os.fdopen(w, 'wb')
        self.exit_stack.callback(self.r.close)
        self.exit_stack.callback(self.w.close)

        self.k.notify_open(r)
        self.k.notify_open(w)

    def tearDown(self):
        self.exit_stack.close()
        super().tearDown()

    def test_disallow_resursive(self):

        async def noop():
            pass

        async def f():
            try:
                self.k.run(noop)
            except AssertionError as exc:
                return exc
            else:
                return None

        exc = self.k.run(f, timeout=1)
        self.assertIsInstance(exc, AssertionError)
        self.assertRegex(str(exc), r'expect.*None')

    def test_sanity_check(self):
        """Test ``Kernel._sanity_check``.

        It should not fail even in a coroutine.
        """

        self.k._sanity_check()

        async def f():
            self.k._sanity_check()

        self.k.run(f)

    def test_check_closed(self):
        self.k.close()
        for method, args in (
            (self.k.run, ()),
            (self.k.spawn, (None, )),
            (self.k.notify_open, (None, )),
            (self.k.notify_close, (None, )),
            (self.k.unblock, (None, )),
            (self.k.cancel, (None, )),
            (self.k.timeout_after, (None, None)),
            (self.k.post_callback, (None, )),
        ):
            with self.subTest(method):
                with self.assertRaisesRegex(AssertionError, r'expect false'):
                    method(*args)
        # These methods can be called even after kernel is closed.
        self.assertEqual(self.k.get_stats(), (0, ) * 10)
        self.assertEqual(self.k.get_current_task(), None)
        self.assertEqual(self.k.get_all_tasks(), [])

    def test_disallow_across_kernel(self):

        async def f():
            pass

        async def join():
            await traps.join(test_task)

        with kernels.Kernel(sanity_check_frequency=1) as k:
            test_task = k.spawn(f)

        with self.assertRaisesRegex(AssertionError, r'expect.*Kernel'):
            self.k.run(join())

        with self.assertRaisesRegex(AssertionError, r'expect.*Kernel'):
            self.k.cancel(test_task)

        with self.assertRaisesRegex(AssertionError, r'expect.*Kernel'):
            self.k.timeout_after(test_task, 0)

    def test_async_generator(self):

        gen_exit = False

        async def gen():
            nonlocal gen_exit
            try:
                yield 1
                yield 2
            finally:
                gen_exit = True

        async def run():
            async for _ in gen():
                break

        self.k.run(run(), timeout=0.01)
        self.assert_stats(
            num_ticks=1,
            num_tasks=0,
            num_ready=0,
            num_async_generators=0,
        )
        self.assertTrue(gen_exit)

    def test_async_generator_in_close(self):

        gen_obj = None  # Keep a strong reference to generator.
        gen_exit = False

        async def gen():
            nonlocal gen_exit
            try:
                yield 1
                yield 2
            finally:
                gen_exit = True

        async def run():
            nonlocal gen_obj
            gen_obj = gen()
            async for _ in gen_obj:
                break

        self.k.run(run(), timeout=0.01)
        self.assert_stats(
            num_ticks=1,
            num_tasks=0,
            num_ready=0,
            num_async_generators=1,
        )
        self.assertFalse(gen_exit)

        self.k.close()
        self.assert_stats(
            num_ticks=1,
            num_tasks=0,
            num_ready=0,
            num_async_generators=1,
        )
        self.assertTrue(gen_exit)

    def test_close_async_generator_blocked(self):

        gen_exit = False

        async def gen():
            nonlocal gen_exit
            try:
                while True:
                    try:
                        yield
                    except BaseException:
                        pass
            finally:
                gen_exit = True

        async def run():
            async for _ in gen():
                break

        with self.assertLogs(kernels.__name__, level='WARNING') as cm:
            self.k.run(run(), timeout=0.01)

        self.assertIn('async generator ignored GeneratorExit', cm.output[0])
        self.assert_stats(
            num_ticks=1,
            num_tasks=0,
            num_ready=0,
            num_async_generators=0,
        )
        self.assertFalse(gen_exit)

    def test_get_current_task(self):

        async def f():
            return self.k.get_current_task()

        self.assertIsNone(self.k.get_current_task())

        task = self.k.spawn(f)
        self.k.run(timeout=1)

        self.assertTrue(task.is_completed())
        self.assertIs(task.get_result_nonblocking(), task)

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

        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)

        actual = self.k.get_all_tasks()
        self.assert_stats(
            num_ticks=1, num_tasks=3, num_poll=1, num_sleep=1, num_blocked=1
        )
        self.assertEqual(set(actual), {t2, t3, t4})

        self.k.cancel(t2)
        self.k.cancel(t3)
        self.k.cancel(t4)
        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)

    def test_get_all_tasks_in_coroutine(self):

        async def f():
            return self.k.get_all_tasks()

        task = self.k.spawn(f)
        self.k.run(timeout=1)

        self.assertTrue(task.is_completed())
        self.assertEqual(task.get_result_nonblocking(), [task])

    def test_timeout(self):

        async def block_forever():
            await traps.poll_read(self.r.fileno())

        self.assert_stats()

        with self.assertRaises(errors.KernelTimeout):
            self.k.run(block_forever, timeout=0)
        self.assert_stats(num_ticks=1, num_tasks=1, num_poll=1)

        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=2, num_tasks=1, num_poll=1)

        with self.assertRaises(errors.KernelTimeout):
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

        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=1, num_tasks=1, num_poll=1, num_timeout=1)

        self.w.write(b'\x00')
        self.w.flush()
        self.k.run(timeout=1)
        self.assert_stats(num_ticks=3, num_tasks=0)

    def test_timeout_after_non_positive(self):

        task = None

        async def do_timeout_after():
            self.k.timeout_after(task, 0)  # Not raised here.
            try:
                await traps.poll_read(self.r.fileno())  # But here.
            except errors.Timeout:
                return 'raised'
            else:
                return 'not raised'

        task = self.k.spawn(do_timeout_after)

        self.k.run(timeout=1)
        self.assertTrue(task.is_completed())
        self.assertEqual(task.get_result_nonblocking(), 'raised')

    def test_timeout_after_none(self):

        task = None

        async def do_timeout_after():
            self.k.timeout_after(task, None)
            await traps.poll_read(self.r.fileno())

        self.assert_stats()

        task = self.k.spawn(do_timeout_after)
        self.assert_stats(num_ticks=0, num_tasks=1, num_ready=1)

        with self.assertRaises(errors.KernelTimeout):
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
        self.assert_stats()

        task = self.k.spawn(traps.poll_read(self.r.fileno()))
        self.assert_stats(num_ticks=0, num_tasks=1, num_ready=1)

        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=1, num_tasks=1, num_poll=1)

        self.k.cancel(task)
        self.assert_stats(
            num_ticks=1, num_tasks=1, num_ready=1, num_to_raise=1
        )

        self.k.run()
        self.assert_stats(num_ticks=2, num_tasks=0)

        with self.assertRaises(errors.Cancelled):
            task.get_result_nonblocking()

    def test_poll(self):

        self.assert_stats()

        with self.assertRaises(errors.KernelTimeout):
            self.k.run(traps.poll_read(self.r.fileno()), timeout=0)
        self.assert_stats(num_ticks=1, num_tasks=1, num_poll=1)

        self.w.write(b'\x00')
        self.w.flush()

        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=2, num_tasks=1, num_ready=1)

        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=3, num_tasks=0, num_poll=0)

    def test_poll_read_and_write(self):
        t1 = self.k.spawn(traps.poll_read(self.r.fileno()))
        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=1, num_tasks=1, num_poll=1)

        t2 = self.k.spawn(traps.poll_write(self.r.fileno()))
        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=2, num_tasks=2, num_poll=2)

        t3 = self.k.spawn(traps.poll_read(self.r.fileno()))
        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=3, num_tasks=3, num_poll=3)

        self.k.cancel(t1)
        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=4, num_tasks=2, num_poll=2)

        self.k.cancel(t2)
        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=5, num_tasks=1, num_poll=1)

        self.k.cancel(t3)
        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=6, num_tasks=0, num_poll=0)

    def test_block(self):

        source = object()
        task = self.k.spawn(traps.block(source))
        self.assert_stats(num_ticks=0, num_tasks=1, num_ready=1)
        self.assertFalse(task.is_completed())

        with self.assertRaises(errors.KernelTimeout):
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
        with self.assertRaises(errors.KernelTimeout):
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

    def assert_poll(self, pair, expect_can_read, expect_can_write):
        self.assertCountEqual(pair[0], expect_can_read)
        self.assertCountEqual(pair[1], expect_can_write)

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

        # ``nudge`` should swallow ``errno.EBADF``.
        for _ in range(8):
            nudger.nudge()

    def test_poller(self):
        poller = pollers.Epoll()
        nudger = kernels.Nudger()
        nudger.register_to(poller)

        self.assert_poll(poller.poll(0), [], [])

        nudger.nudge()
        self.assert_poll(poller.poll(0), [nudger._r], [])

        nudger.ack()
        self.assert_poll(poller.poll(0), [], [])

        poller.close()
        nudger.close()


if __name__ == '__main__':
    unittest.main()
