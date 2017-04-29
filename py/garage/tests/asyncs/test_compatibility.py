import unittest

from tests.availability import curio_available

import types

if curio_available:
    import curio
    import curio.traps
    from garage.asyncs.utils import synchronous


@unittest.skipUnless(curio_available, 'curio unavailable')
class CompatibilityTest(unittest.TestCase):
    """As curio is in pre-1.0, its API is still unstable.  Let's check
       our basic assumptions about curio API.

       (Also test the internal API we are using is still there.)
    """

    @synchronous
    async def test_task(self):
        async def f():
            pass
        task = await curio.spawn(f)

        self.assertTrue(hasattr(task, 'next_value'))
        self.assertTrue(hasattr(task, 'next_exc'))
        self.assertTrue(hasattr(task, 'state'))
        self.assertTrue(hasattr(task, 'cancel_func'))

        self.assertTrue(hasattr(task, '_send'))
        self.assertTrue(hasattr(task, '_throw'))

        self.assertTrue(hasattr(task, '_ignore_result'))
        self.assertTrue(hasattr(task, '_taskgroup'))

        # asyncs.base.Event uses 'READY' state; make sure we have it
        self.assertEqual('READY', task.state)

        await task.join()

    def test_task_group(self):
        self.assertTrue(hasattr(curio.TaskGroup, '_task_done'))
        self.assertTrue(hasattr(curio.TaskGroup, '_task_discard'))

    @synchronous
    async def test_event_set(self):
        event = curio.Event()
        coro = event.set()
        self.assertTrue(isinstance(coro, types.CoroutineType))
        await coro

    @synchronous
    async def test_event_clear(self):
        event = curio.Event()
        not_coro = event.clear()
        try:
            self.assertFalse(isinstance(not_coro, types.CoroutineType))
        except AssertionError:
            await coro
            raise

    @synchronous
    async def test_traps_scheduler_wait(self):
        self.assertTrue(hasattr(curio.traps, '_scheduler_wait'))

        event = curio.Event()

        coro = event.wait()
        trap, sched, state = coro.send(None)
        self.assertEqual(curio.traps.Traps._trap_sched_wait, trap)
        self.assertEqual(0, len(sched))
        self.assertEqual(state, 'EVENT_WAIT')

        await event.set()

        with self.assertRaises(StopIteration):
            coro.send(None)

    @synchronous
    async def test_traps_get_kernel(self):
        self.assertIsNotNone(await curio.traps._get_kernel())


if __name__ == '__main__':
    unittest.main()
