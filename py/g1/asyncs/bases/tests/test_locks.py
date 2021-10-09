import unittest

from g1.asyncs.bases import locks
from g1.asyncs.kernels import contexts
from g1.asyncs.kernels import errors
from g1.asyncs.kernels import kernels


class LockTest(unittest.TestCase):

    def setUp(self):
        self.k = kernels.Kernel()
        self.token = contexts.set_kernel(self.k)

    def tearDown(self):
        contexts.KERNEL.reset(self.token)
        self.k.close()

    def test_lock(self):
        l = locks.Lock()

        # Error because you are not owner.
        with self.assertRaisesRegex(AssertionError, r'expect true'):
            l.release()

        t1 = self.k.spawn(l.acquire)
        self.k.run(timeout=1)
        self.assertEqual(self.k.get_stats().num_blocked, 0)
        self.assertTrue(t1.is_completed())
        self.assertTrue(t1.get_result_nonblocking())
        self.assertEqual(len(self.k._generic_blocker), 0)

        t2 = self.k.spawn(l.acquire)
        t3 = self.k.spawn(l.acquire)
        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assertEqual(self.k.get_stats().num_blocked, 2)
        self.assertFalse(t2.is_completed())
        self.assertFalse(t3.is_completed())
        self.assertEqual(len(self.k._generic_blocker), 2)

        l.release()
        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assertEqual(self.k.get_stats().num_blocked, 1)
        self.assertEqual(len(self.k._generic_blocker), 1)

        l.release()
        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assertEqual(self.k.get_stats().num_blocked, 0)
        self.assertTrue(t2.is_completed())
        self.assertTrue(t2.get_result_nonblocking())
        self.assertTrue(t3.is_completed())
        self.assertTrue(t3.get_result_nonblocking())
        self.assertEqual(len(self.k._generic_blocker), 0)

    def test_nonblocking(self):
        l = locks.Lock()
        self.assertTrue(self.k.run(l.acquire(blocking=False), timeout=1))
        self.assertFalse(self.k.run(l.acquire(blocking=False), timeout=1))
        self.assertEqual(self.k.get_stats().num_blocked, 0)
        self.assertEqual(self.k.get_stats().num_tasks, 0)
        self.assertEqual(len(self.k._generic_blocker), 0)


class ConditionTest(unittest.TestCase):

    def setUp(self):
        self.k = kernels.Kernel()
        self.token = contexts.set_kernel(self.k)

    def tearDown(self):
        contexts.KERNEL.reset(self.token)
        self.k.close()

    def assert_num_waiters(self, cv, num_waiters):
        self.assertEqual(len(cv._waiters), num_waiters)

    def test_condition(self):

        cv = locks.Condition()
        self.assert_num_waiters(cv, 0)

        num_returned = 0

        async def wait_cv():
            nonlocal num_returned
            async with cv:
                self.assertTrue(cv._lock._locked)
                await cv.wait()
                self.assertTrue(cv._lock._locked)
            self.assertFalse(cv._lock._locked)
            num_returned += 1

        ts = [self.k.spawn(wait_cv) for _ in range(3)]

        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assertEqual(self.k.get_stats().num_blocked, 3)
        self.assertEqual(len(self.k._generic_blocker), 3)
        self.assertEqual(num_returned, 0)
        self.assert_num_waiters(cv, 3)

        self.assertTrue(cv.acquire_nonblocking())
        cv.notify()
        cv.release()

        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assertEqual(self.k.get_stats().num_blocked, 2)
        self.assertEqual(len(self.k._generic_blocker), 2)
        self.assertEqual(num_returned, 1)
        self.assert_num_waiters(cv, 2)

        self.assertTrue(cv.acquire_nonblocking())
        cv.notify()
        cv.release()

        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assertEqual(self.k.get_stats().num_blocked, 1)
        self.assertEqual(len(self.k._generic_blocker), 1)
        self.assertEqual(num_returned, 2)
        self.assert_num_waiters(cv, 1)

        self.assertTrue(cv.acquire_nonblocking())
        cv.notify()
        cv.release()

        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assertEqual(self.k.get_stats().num_blocked, 0)
        self.assertEqual(len(self.k._generic_blocker), 0)
        self.assertEqual(num_returned, 3)
        self.assert_num_waiters(cv, 0)

        for t in ts:
            self.assertTrue(t.is_completed())
            t.get_result_nonblocking()

    def test_notify_empty(self):
        cv = locks.Condition()
        self.assertTrue(cv.acquire_nonblocking())
        self.assert_num_waiters(cv, 0)
        cv.notify()
        self.assert_num_waiters(cv, 0)
        cv.notify(999)

    def test_unlocked_error(self):
        cv = locks.Condition()
        # Error because you are not owner.
        with self.assertRaisesRegex(AssertionError, 'expect true'):
            self.k.run(cv.wait)
        with self.assertRaisesRegex(AssertionError, 'expect true'):
            cv.notify()


class EventTest(unittest.TestCase):

    def setUp(self):
        self.k = kernels.Kernel()
        self.token = contexts.set_kernel(self.k)

    def tearDown(self):
        contexts.KERNEL.reset(self.token)
        self.k.close()

    def test_event(self):
        e = locks.Event()
        self.assertFalse(e.is_set())

        e.set()
        self.assertTrue(e.is_set())
        e.set()  # You may call it repeatedly.
        self.assertTrue(e.is_set())
        e.clear()
        self.assertFalse(e.is_set())
        e.clear()  # You may call it repeatedly.
        self.assertFalse(e.is_set())

        e.set()
        self.assertTrue(self.k.run(e.wait, timeout=1))
        self.assertEqual(self.k.get_stats().num_blocked, 0)
        self.assertEqual(len(self.k._generic_blocker), 0)

        e.clear()
        with self.assertRaises(errors.KernelTimeout):
            self.k.run(e.wait, timeout=0)
        self.assertEqual(self.k.get_stats().num_blocked, 1)
        self.assertEqual(len(self.k._generic_blocker), 1)

        e.set()
        self.assertTrue(self.k.run(e.wait, timeout=1))
        self.assertEqual(self.k.get_stats().num_blocked, 0)
        self.assertEqual(len(self.k._generic_blocker), 0)


class EventWithoutKernelTest(unittest.TestCase):

    def test_event(self):
        with self.assertRaises(LookupError):
            contexts.get_kernel()

        e = locks.Event()
        self.assertFalse(e.is_set())

        e.set()
        self.assertTrue(e.is_set())
        e.set()  # You may call it repeatedly.
        self.assertTrue(e.is_set())
        e.clear()
        self.assertFalse(e.is_set())
        e.clear()  # You may call it repeatedly.
        self.assertFalse(e.is_set())


class GateTest(unittest.TestCase):

    def setUp(self):
        self.k = kernels.Kernel()
        self.token = contexts.set_kernel(self.k)

    def tearDown(self):
        contexts.KERNEL.reset(self.token)
        self.k.close()

    def test_unblock(self):
        g = locks.Gate()

        t = self.k.spawn(g.wait)
        self.assertEqual(self.k.get_stats().num_blocked, 0)

        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assertEqual(self.k.get_stats().num_blocked, 1)

        g.unblock()

        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assertEqual(self.k.get_stats().num_blocked, 0)
        self.assertTrue(t.is_completed())

    def test_unblock_before_wait(self):
        g = locks.Gate()

        async def func():
            g.unblock()
            await g.wait()

        t = self.k.spawn(func)
        self.assertEqual(self.k.get_stats().num_blocked, 0)

        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assertEqual(self.k.get_stats().num_blocked, 1)

        g.unblock()

        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assertEqual(self.k.get_stats().num_blocked, 0)
        self.assertTrue(t.is_completed())


class GateWithoutKernelTest(unittest.TestCase):

    def test_gate(self):
        with self.assertRaises(LookupError):
            contexts.get_kernel()
        g = locks.Gate()
        g.unblock()


class SemaphoreTest(unittest.TestCase):

    def setUp(self):
        self.k = kernels.Kernel()
        self.token = contexts.set_kernel(self.k)

    def tearDown(self):
        contexts.KERNEL.reset(self.token)
        self.k.close()

    def test_semaphore(self):
        with self.assertRaisesRegex(
            AssertionError,
            r'expect x >= 0, not -1',
        ):
            locks.Semaphore(-1)

        s = locks.Semaphore()
        self.do_test_semaphore(s)
        s.release()
        self.assertEqual(s._value, 1)
        s.release()
        self.assertEqual(s._value, 2)

    def test_bounded_semaphore(self):
        with self.assertRaisesRegex(
            AssertionError,
            r'expect x >= 0, not -1',
        ):
            locks.BoundedSemaphore(-1)

        s = locks.BoundedSemaphore()
        self.do_test_semaphore(s)
        s.release()
        self.assertEqual(s._value, 1)
        with self.assertRaisesRegex(
            AssertionError,
            r'expect x <= 1, not 2',
        ):
            s.release()

    def do_test_semaphore(self, s):
        self.assertEqual(s._value, 1)

        t1 = self.k.spawn(s.acquire)
        self.k.run(timeout=1)
        self.assertEqual(self.k.get_stats().num_blocked, 0)
        self.assertTrue(t1.is_completed())
        self.assertTrue(t1.get_result_nonblocking())
        self.assertEqual(len(self.k._generic_blocker), 0)
        self.assertEqual(s._value, 0)

        t2 = self.k.spawn(s.acquire)
        t3 = self.k.spawn(s.acquire)
        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assertEqual(self.k.get_stats().num_blocked, 2)
        self.assertFalse(t2.is_completed())
        self.assertFalse(t3.is_completed())
        self.assertEqual(len(self.k._generic_blocker), 2)
        self.assertEqual(s._value, 0)

        s.release()
        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assertEqual(self.k.get_stats().num_blocked, 1)
        self.assertEqual(len(self.k._generic_blocker), 1)
        self.assertEqual(s._value, 0)

        s.release()
        with self.assertRaises(errors.KernelTimeout):
            self.k.run(timeout=0)
        self.assertEqual(self.k.get_stats().num_blocked, 0)
        self.assertTrue(t2.is_completed())
        self.assertTrue(t2.get_result_nonblocking())
        self.assertTrue(t3.is_completed())
        self.assertTrue(t3.get_result_nonblocking())
        self.assertEqual(len(self.k._generic_blocker), 0)
        self.assertEqual(s._value, 0)

    def test_nonblocking(self):
        s = locks.Semaphore(2)
        self.assertTrue(self.k.run(s.acquire(blocking=False), timeout=1))
        self.assertTrue(self.k.run(s.acquire(blocking=False), timeout=1))
        self.assertFalse(self.k.run(s.acquire(blocking=False), timeout=1))
        self.assertEqual(self.k.get_stats().num_blocked, 0)
        self.assertEqual(self.k.get_stats().num_tasks, 0)
        self.assertEqual(len(self.k._generic_blocker), 0)


if __name__ == '__main__':
    unittest.main()
