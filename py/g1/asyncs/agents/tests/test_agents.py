import unittest
import unittest.mock

import re

from g1.asyncs import agents
from g1.asyncs import kernels
from g1.asyncs.bases import locks
from g1.asyncs.bases import queues
from g1.asyncs.bases import tasks
from g1.asyncs.bases import timers


class SuperviseAgentsTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.main_task = None
        self.agent_queue = tasks.CompletionQueue()
        self.graceful_exit = locks.Event()
        self.signal_queue = queues.Queue()
        mock = unittest.mock.patch(agents.__name__ + '.signals').start()
        mock.SignalSource().__enter__().get = self.signal_queue.get
        self._assert_logs = self.assertLogs(agents.__name__, level='DEBUG')
        self.cm = self._assert_logs.__enter__()

    def tearDown(self):
        unittest.mock.patch.stopall()
        self._assert_logs.__exit__(None, None, None)
        super().tearDown()

    def assert_(self, closed, queue_size, graceful_exit, log_patterns):
        self.assertEqual(self.agent_queue.is_closed(), closed)
        self.assertEqual(len(self.agent_queue), queue_size)
        self.assertEqual(self.graceful_exit.is_set(), graceful_exit)
        message = 'expect patterns %r in %r' % (log_patterns, self.cm.output)
        if len(self.cm.output) != len(log_patterns):
            self.fail(message)
        for log_line, log_pattern in zip(self.cm.output, log_patterns):
            if not re.search(log_pattern, log_line):
                self.fail(message)

    def run_supervisor(self):
        self.main_task = tasks.spawn(
            agents.supervise_agents(self.agent_queue, self.graceful_exit, 5)
        )
        kernels.run(timeout=0.01)

    @kernels.with_kernel
    def test_graceful_exit_by_user(self):
        self.graceful_exit.set()
        self.run_supervisor()
        self.assert_(True, 0, True, [r'graceful exit: requested by user'])
        self.assertIsNone(self.main_task.get_result_nonblocking())
        self.assertFalse(tasks.get_all_tasks())

    @kernels.with_kernel
    def test_signal(self):
        self.signal_queue.put_nonblocking(1)
        self.run_supervisor()
        self.assert_(True, 0, True, [r'graceful exit: receive signal: 1'])
        self.assertIsNone(self.main_task.get_result_nonblocking())
        self.assertFalse(tasks.get_all_tasks())

    @kernels.with_kernel
    def test_repeated_signals(self):
        sleep_task = self.agent_queue.spawn(timers.sleep(99))
        self.assert_(False, 1, False, [])

        self.signal_queue.put_nonblocking(1)
        with self.assertRaises(kernels.KernelTimeout):
            self.run_supervisor()
        self.assert_(True, 1, True, [r'graceful exit: receive signal: 1'])

        self.signal_queue.put_nonblocking(2)
        kernels.run(timeout=1)
        self.assert_(True, 0, True, [r'graceful exit: receive signal: 1'])

        with self.assertRaisesRegex(
            agents.SupervisorError,
            r'receive signal during graceful exit: 2',
        ):
            self.main_task.get_result_nonblocking()
        with self.assertRaises(tasks.Cancelled):
            sleep_task.get_result_nonblocking()
        self.assertFalse(tasks.get_all_tasks())

    @kernels.with_kernel
    def test_agent_exit(self):
        noop_task = self.agent_queue.spawn(noop)
        self.assert_(False, 1, False, [])
        self.run_supervisor()
        self.assert_(True, 0, True, [r'no op', r'graceful exit: agent exit: '])
        self.assertIsNone(noop_task.get_result_nonblocking())
        self.assertFalse(tasks.get_all_tasks())

    @kernels.with_kernel
    def test_agent_error(self):
        raises_task = self.agent_queue.spawn(raises(ValueError('some error')))
        self.assert_(False, 1, False, [])
        self.run_supervisor()
        self.assert_(True, 0, False, [])
        with self.assertRaisesRegex(
            agents.SupervisorError,
            r'agent err out: ',
        ):
            self.main_task.get_result_nonblocking()
        with self.assertRaisesRegex(ValueError, r'some error'):
            raises_task.get_result_nonblocking()
        self.assertFalse(tasks.get_all_tasks())
        # Make self._assert_logs.__exit__ happy.
        agents.LOG.debug('dummy')

    @kernels.with_kernel
    def test_grace_period_exceeded(self):
        self.graceful_exit.set()
        sleep_task = self.agent_queue.spawn(timers.sleep(99))
        self.assert_(False, 1, True, [])
        self.main_task = tasks.spawn(
            agents.supervise_agents(self.agent_queue, self.graceful_exit, 0)
        )
        kernels.run(timeout=0.01)
        self.assert_(True, 0, True, [r'graceful exit: requested by user'])
        with self.assertRaisesRegex(
            agents.SupervisorError,
            r'grace period exceeded',
        ):
            self.main_task.get_result_nonblocking()
        with self.assertRaises(tasks.Cancelled):
            sleep_task.get_result_nonblocking()
        self.assertFalse(tasks.get_all_tasks())


async def noop():
    agents.LOG.debug('no op')


async def raises(exc):
    raise exc


if __name__ == '__main__':
    unittest.main()
