import unittest
import unittest.mock

import re

from g1.asyncs import kernels
from g1.asyncs import servers
from g1.asyncs.bases import locks
from g1.asyncs.bases import tasks
from g1.asyncs.bases import timers


class LoggerMixin:

    def setUp(self):
        self._cxt = self.assertLogs(servers.__name__, level='DEBUG')
        self.cm = self._cxt.__enter__()

    def tearDown(self):
        self._cxt.__exit__(None, None, None)

    def assert_logs(self, log_lines, log_patterns):
        message = 'expect log patterns %r in %r' % (log_patterns, log_lines)
        if len(log_lines) != len(log_patterns):
            self.fail(message)
        for log_line, log_pattern in zip(log_lines, log_patterns):
            if not re.search(log_pattern, log_line):
                self.fail(message)


class SuperviseServersTest(LoggerMixin, unittest.TestCase):

    def setUp(self):

        async def mocked_handle_signal(graceful_exit):
            for _ in range(2):
                await self.mocked_signal.wait()
                servers.LOG.debug('receive mocked signal')
                graceful_exit.set()
                self.mocked_signal.clear()

        super().setUp()

        self.mocked_signal = locks.Event()
        self.ge = locks.Event()
        self.tq = tasks.CompletionQueue()

        unittest.mock.patch(
            servers.__name__ + '.handle_signal',
            mocked_handle_signal,
        ).start()

    def tearDown(self):
        super().tearDown()
        unittest.mock.patch.stopall()

    def run_supervise_servers(self, grace_period, timeout):
        return kernels.run(
            servers.supervise_servers(self.tq, self.ge, grace_period),
            timeout=timeout,
        )

    def assert_state(self, exited, closed, queue_size, log_patterns):
        self.assertEqual(self.ge.is_set(), exited)
        self.assertEqual(self.tq.is_closed(), closed)
        self.assertEqual(len(self.tq), queue_size)
        self.assert_logs(self.cm.output, log_patterns)

    @kernels.with_kernel
    def test_graceful_exit(self):
        self.ge.set()
        self.assert_state(True, False, 0, [])
        self.assertIsNone(self.run_supervise_servers(5, 1))
        self.assert_state(True, True, 0, [
            r'initiate graceful exit$',
        ])
        self.assertEqual(tasks.get_all_tasks(), [])

    @kernels.with_kernel
    def test_signal(self):
        self.assert_state(False, False, 0, [])
        self.mocked_signal.set()
        self.assertIsNone(self.run_supervise_servers(5, 1))
        self.assert_state(
            True, True, 0, [
                r'receive mocked signal',
                r'initiate graceful exit$',
            ]
        )
        self.assertEqual(tasks.get_all_tasks(), [])

    @kernels.with_kernel
    def test_repeated_signals(self):
        t = tasks.spawn(timers.sleep(99))
        self.tq.put(t)
        self.assert_state(False, False, 1, [])

        self.mocked_signal.set()
        with self.assertRaises(kernels.KernelTimeout):
            self.run_supervise_servers(5, 0)
        self.assert_state(
            True, True, 2, [
                r'receive mocked signal',
                r'initiate graceful exit$',
            ]
        )
        self.assertFalse(self.mocked_signal.is_set())

        self.mocked_signal.set()
        self.assertIsNone(kernels.run(timeout=1))
        self.assert_state(
            True, True, 0, [
                r'receive mocked signal',
                r'initiate graceful exit$',
                r'receive mocked signal',
                r'initiate non-graceful exit due to repeated signals',
            ]
        )

        with self.assertRaises(tasks.Cancelled):
            t.get_result_nonblocking()

        self.assertEqual(tasks.get_all_tasks(), [])

    @kernels.with_kernel
    def test_server_exit(self):
        t = tasks.spawn(noop)
        self.tq.put(t)
        self.assert_state(False, False, 1, [])
        self.assertIsNone(self.run_supervise_servers(5, 1))
        self.assert_state(
            True, True, 0, [
                r'no op',
                r'initiate graceful exit due to server task exit',
            ]
        )
        self.assertIsNone(t.get_result_nonblocking())
        self.assertEqual(tasks.get_all_tasks(), [])

    @kernels.with_kernel
    def test_server_error(self):
        t = tasks.spawn(raises(ValueError('some error')))
        self.tq.put(t)
        self.assert_state(False, False, 1, [])
        with self.assertRaises(servers.SupervisorError):
            self.run_supervise_servers(5, 1)
        self.assert_state(
            False, True, 0, [
                r'initiate non-graceful exit due to server task error',
            ]
        )
        with self.assertRaisesRegex(ValueError, r'some error'):
            t.get_result_nonblocking()
        self.assertEqual(tasks.get_all_tasks(), [])

    @kernels.with_kernel
    def test_grace_period(self):
        self.ge.set()
        t = tasks.spawn(timers.sleep(99))
        self.tq.put(t)
        self.assert_state(True, False, 1, [])
        with self.assertRaises(servers.SupervisorError):
            self.run_supervise_servers(0, 1)
        self.assert_state(
            True, True, 0, [
                r'initiate graceful exit$',
                r'initiate non-graceful exit due to grace period exceeded',
            ]
        )
        with self.assertRaises(tasks.Cancelled):
            t.get_result_nonblocking()
        self.assertEqual(tasks.get_all_tasks(), [])


class SuperviseHandlersTest(LoggerMixin, unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.tq = tasks.CompletionQueue()

    def assert_state(self, closed, queue_size, log_patterns):
        self.assertEqual(self.tq.is_closed(), closed)
        self.assertEqual(len(self.tq), queue_size)
        self.assert_logs(self.cm.output, log_patterns)

    def run_supervise_handlers(self, helper_tasks, timeout):
        return kernels.run(
            servers.supervise_handlers(self.tq, helper_tasks),
            timeout=timeout,
        )

    @kernels.with_kernel
    def test_helper_exit(self):
        t = tasks.spawn(noop)
        self.tq.put(t)
        self.assert_state(False, 1, [])
        self.assertIsNone(self.run_supervise_handlers((t, ), 1))
        self.assert_state(True, 0, [
            r'no op',
            r'server helper task exit:',
        ])
        self.assertIsNone(t.get_result_nonblocking())
        self.assertEqual(tasks.get_all_tasks(), [])

    @kernels.with_kernel
    def test_helper_error(self):
        t = tasks.spawn(raises(ValueError('some error')))
        self.tq.put(t)
        self.assert_state(False, 1, [])
        with self.assertRaises(servers.SupervisorError):
            self.run_supervise_handlers((t, ), 1)
        self.assert_state(True, 0, [
            r'server helper task error:',
        ])
        with self.assertRaisesRegex(ValueError, r'some error'):
            t.get_result_nonblocking()
        self.assertEqual(tasks.get_all_tasks(), [])

    @kernels.with_kernel
    def test_handler_exit(self):
        e = locks.Event()
        t = tasks.spawn(e.wait)
        self.tq.put(t)
        self.tq.put(tasks.spawn(noop))
        self.assert_state(False, 2, [])
        with self.assertRaises(kernels.KernelTimeout):
            self.run_supervise_handlers((t, ), 0)
        self.assert_state(False, 1, [
            r'no op',
            r'handler task exit:',
        ])
        e.set()
        self.assertIsNone(kernels.run(timeout=1))
        self.assert_state(
            True, 0, [
                r'no op',
                r'handler task exit:',
                r'server helper task exit:',
            ]
        )
        self.assertTrue(t.get_result_nonblocking())
        self.assertEqual(tasks.get_all_tasks(), [])

    @kernels.with_kernel
    def test_handler_error(self):
        e = locks.Event()
        t = tasks.spawn(e.wait)
        self.tq.put(t)
        self.tq.put(tasks.spawn(raises(ValueError('some error'))))
        self.assert_state(False, 2, [])
        with self.assertRaises(kernels.KernelTimeout):
            self.run_supervise_handlers((t, ), 0)
        self.assert_state(False, 1, [
            r'handler task error:',
        ])
        e.set()
        self.assertIsNone(kernels.run(timeout=1))
        self.assert_state(
            True, 0, [
                r'handler task error:',
                r'server helper task exit:',
            ]
        )
        self.assertTrue(t.get_result_nonblocking())
        self.assertEqual(tasks.get_all_tasks(), [])


async def noop():
    servers.LOG.debug('no op')


async def raises(exc):
    raise exc


if __name__ == '__main__':
    unittest.main()
