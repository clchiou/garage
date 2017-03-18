import unittest

from tests.availability import curio_available

from concurrent.futures import Future as _Future

if curio_available:
    import curio
    from garage.asyncs.futures import CancelledError, Future, FutureAdapter

from tests.asyncs.utils import synchronous


@unittest.skipUnless(curio_available, 'curio unavailable')
class FutureTest(unittest.TestCase):

    @synchronous
    async def test_result(self):

        f = Future()
        p = f.promise()
        self.assertFalse(f.running())
        self.assertTrue(p.set_running_or_notify_cancel())
        self.assertTrue(f.running())

        p.set_result(1)

        self.assertTrue(f.done())
        self.assertEqual(1, await f.result())
        self.assertIsNone(await f.exception())

        with self.assertRaisesRegex(AssertionError, 'marked FINISHED'):
            p.set_result(1)

    @synchronous
    async def test_exception(self):

        f = Future()
        p = f.promise()

        exc = ValueError('test exception')
        p.set_exception(exc)

        # Note: we can't use assertRaises here because for some reason
        # it clears stack frame of the task, and that will cause CPython
        # to raise a RuntimeError with message:
        #   cannot reuse already awaited coroutine
        # See Objects/genobject.c for more details.
        try:
            await f.result()
            self.fail('get_result() did not raise')
        except ValueError as e:
            self.assertEqual(exc, e)
        self.assertEqual(exc, await f.exception())

    @synchronous
    async def test_cancel(self):

        f = Future()
        p = f.promise()

        f.cancel()
        self.assertFalse(p.set_running_or_notify_cancel())

        # Since Future is cancelled, calls to Promise are ignored.
        p.set_result(99)
        p.set_exception(ValueError())

        with self.assertRaises(CancelledError):
            await f.result()
        with self.assertRaises(CancelledError):
            await f.exception()


@unittest.skipUnless(curio_available, 'curio unavailable')
class FutureAdapterTest(unittest.TestCase):

    @synchronous
    async def test_result(self):
        f = FutureAdapter(_Future())

        async with curio.ignore_after(0.01):
            await f.result()
            self.fail('result should not be available')

        f._future.set_result(1)

        self.assertEqual(1, await f.result())

    @synchronous
    async def test_exception(self):
        f = FutureAdapter(_Future())
        exc = ValueError('test exception')
        f._future.set_exception(exc)
        try:
            await f.result()
            self.fail('get_result() did not raise')
        except ValueError as e:
            self.assertEqual(exc, e)
        self.assertEqual(exc, await f.exception())

    @synchronous
    async def test_cancel(self):
        f = FutureAdapter(_Future())
        self.assertTrue(f.cancel())
        with self.assertRaises(CancelledError):
            await f.result()
        with self.assertRaises(CancelledError):
            await f.exception()

        f = FutureAdapter(_Future())
        f._future.set_running_or_notify_cancel()
        self.assertFalse(f.cancel())


if __name__ == '__main__':
    unittest.main()
