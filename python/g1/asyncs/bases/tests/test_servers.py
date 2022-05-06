import unittest

import re

from g1.asyncs import kernels
from g1.asyncs.bases import locks
from g1.asyncs.bases import servers
from g1.asyncs.bases import tasks


class SuperviseServerTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.queue = tasks.CompletionQueue()
        self._assert_logs = self.assertLogs(servers.__name__, level='DEBUG')
        self.cm = self._assert_logs.__enter__()

    def tearDown(self):
        self._assert_logs.__exit__(None, None, None)
        super().tearDown()

    def assert_state(self, closed, queue_size, log_patterns):
        self.assertEqual(self.queue.is_closed(), closed)
        self.assertEqual(len(self.queue), queue_size)
        message = 'expect patterns %r in %r' % (log_patterns, self.cm.output)
        if len(self.cm.output) != len(log_patterns):
            self.fail(message)
        for log_line, log_pattern in zip(self.cm.output, log_patterns):
            if not re.search(log_pattern, log_line):
                self.fail(message)

    def run_supervisor(self, server_tasks):
        return kernels.run(
            servers.supervise_server(self.queue, server_tasks),
            timeout=0.01,
        )

    @kernels.with_kernel
    def test_server_exit(self):
        server_task = self.queue.spawn(noop)
        self.assert_state(False, 1, [])
        self.assertIsNone(self.run_supervisor([server_task]))
        self.assert_state(True, 0, [r'no op', r'server task exit: '])
        self.assertIsNone(server_task.get_result_nonblocking())
        self.assertFalse(tasks.get_all_tasks(), [])

    @kernels.with_kernel
    def test_server_error(self):
        server_task = self.queue.spawn(raises(ValueError('some error')))
        self.assert_state(False, 1, [])
        with self.assertRaisesRegex(
            servers.ServerError,
            r'server task error: ',
        ):
            self.run_supervisor([server_task])
        self.assert_state(True, 0, [])
        with self.assertRaisesRegex(ValueError, r'some error'):
            server_task.get_result_nonblocking()
        self.assertFalse(tasks.get_all_tasks(), [])
        # Make self._assert_logs.__exit__ happy.
        servers.LOG.debug('dummy')

    @kernels.with_kernel
    def test_handler_exit(self):
        event = locks.Event()
        server_task = self.queue.spawn(event.wait)
        self.queue.spawn(noop)
        self.assert_state(False, 2, [])
        with self.assertRaises(kernels.KernelTimeout):
            self.run_supervisor([server_task])
        self.assert_state(False, 1, [r'no op', r'handler task exit: '])
        event.set()
        self.assertIsNone(kernels.run(timeout=1))
        self.assert_state(
            True,
            0,
            [r'no op', r'handler task exit: ', r'server task exit: '],
        )
        self.assertTrue(server_task.get_result_nonblocking())
        self.assertFalse(tasks.get_all_tasks(), [])

    @kernels.with_kernel
    def test_handler_error(self):
        event = locks.Event()
        server_task = self.queue.spawn(event.wait)
        self.queue.spawn(raises(ValueError('some error')))
        self.assert_state(False, 2, [])
        with self.assertRaises(kernels.KernelTimeout):
            self.run_supervisor([server_task])
        self.assert_state(False, 1, [r'handler task error: '])
        event.set()
        self.assertIsNone(kernels.run(timeout=1))
        self.assert_state(
            True, 0, [r'handler task error: ', r'server task exit: ']
        )
        self.assertTrue(server_task.get_result_nonblocking())
        self.assertFalse(tasks.get_all_tasks(), [])


async def noop():
    servers.LOG.debug('no op')


async def raises(exc):
    raise exc


if __name__ == '__main__':
    unittest.main()
