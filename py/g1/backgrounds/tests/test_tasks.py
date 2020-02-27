import unittest
import unittest.mock

import g1.asyncs.kernels.errors
import g1.backgrounds.tasks
from g1.asyncs import kernels
from g1.asyncs.bases import tasks
from g1.asyncs.bases import timers


class BackgroundTasksTest(unittest.TestCase):

    def assert_completed(self, task):
        self.assertTrue(task.is_completed())
        self.assertIsNone(task.get_exception_nonblocking())

    def assert_cancelled(self, task):
        self.assertTrue(task.is_completed())
        self.assertIsInstance(
            task.get_exception_nonblocking(), tasks.Cancelled
        )

    @kernels.with_kernel
    @unittest.mock.patch(g1.backgrounds.tasks.__name__ + '._cleanup')
    def test_supervise(self, mock_cleanup):

        async def noop():
            pass

        bg = g1.backgrounds.tasks.BackgroundTasks()
        noop_tasks = [bg.queue.spawn(noop()) for _ in range(3)]
        supervisor_task = tasks.spawn(bg.supervise())
        with self.assertLogs(
            g1.backgrounds.tasks.__name__, level='DEBUG'
        ) as cm:
            with self.assertRaises(kernels.KernelTimeout):
                kernels.run(timeout=0.01)
            # _cleanup should not be called because supervisor_task is
            # cancelled.
            supervisor_task.cancel()
            kernels.run(timeout=0.01)
        self.assert_cancelled(supervisor_task)
        for noop_task in noop_tasks:
            self.assert_completed(noop_task)
        self.assertEqual(len(cm.output), len(noop_tasks))
        for log_line in cm.output:
            self.assertIn('background task exit: ', log_line)
        mock_cleanup.assert_not_called()

    @kernels.with_kernel
    def test_shutdown(self):

        async def catch(caughts):
            try:
                await timers.sleep(None)
            except BaseException as exc:
                caughts.append(exc)
                raise

        async def shutdown(bg):
            await timers.sleep(0.01)
            bg.shutdown()

        caughts = []
        bg = g1.backgrounds.tasks.BackgroundTasks()
        catch_tasks = [bg.queue.spawn(catch(caughts)) for _ in range(3)]
        shutdown_tasks = [tasks.spawn(shutdown(bg)) for _ in range(10)]
        supervisor_task = tasks.spawn(bg.supervise())
        with self.assertLogs(
            g1.backgrounds.tasks.__name__, level='DEBUG'
        ) as cm:
            kernels.run(timeout=0.1)
        self.assert_completed(supervisor_task)
        for catch_task in catch_tasks:
            self.assert_cancelled(catch_task)
        for shutdown_task in shutdown_tasks:
            self.assert_completed(shutdown_task)
        self.assertEqual(len(caughts), len(catch_tasks))
        for caught in caughts:
            self.assertIsInstance(
                caught, g1.asyncs.kernels.errors.TaskCancellation
            )
        self.assertEqual(len(cm.output), 1)
        self.assertIn('cancel 3 background tasks on exit', cm.output[0])


if __name__ == '__main__':
    unittest.main()
