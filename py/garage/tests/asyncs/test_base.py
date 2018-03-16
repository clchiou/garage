import unittest

from tests.availability import curio_available

import types

if curio_available:
    import curio
    from garage.asyncs import base
    from garage.asyncs.utils import synchronous
else:
    def synchronous(func):
        return func


@unittest.skipUnless(curio_available, 'curio unavailable')
class BaseTest(unittest.TestCase):

    @synchronous
    async def test_event(self):

        num_waiters = 3
        num_started = 0
        all_started = curio.Event()

        event = base.Event()

        async def wait_event():
            nonlocal num_started
            num_started += 1
            if num_started == num_waiters:
                await all_started.set()
            await event.wait()

        self.assertFalse(event.is_set())

        tasks = [await curio.spawn(wait_event()) for _ in range(num_waiters)]
        self.assertEqual(
            [False] * num_waiters,
            [task.terminated for task in tasks],
        )

        await all_started.wait()
        event.set()

        for task in tasks:
            await task.join()
        self.assertEqual(
            [True] * num_waiters,
            [task.terminated for task in tasks],
        )

        self.assertTrue(event.is_set())

        event.clear()
        self.assertFalse(event.is_set())


if __name__ == '__main__':
    unittest.main()
