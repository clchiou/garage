import unittest

from collections import namedtuple

from garage.asyncs.watchdogs import Watchdog


Log = namedtuple('Log', 'delay callback handle')


class MockLoop:

    def __init__(self):
        self.logs = []

    def call_later(self, delay, callback):
        handle = MockHandle()
        self.logs.append(Log(delay, callback, handle))
        return handle


class MockHandle:

    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class WatchdogTest(unittest.TestCase):

    def test_watchdog_mock(self):
        loop = MockLoop()
        self.assertListEqual([], loop.logs)

        watchdog = Watchdog(10, self.fail, loop=loop)
        self.assertListEqual([], loop.logs)

        watchdog.start()
        self.assertEqual(1, len(loop.logs))
        self.assertFalse(loop.logs[0].handle.cancelled)

        watchdog.restart()
        self.assertEqual(2, len(loop.logs))
        self.assertTrue(loop.logs[0].handle.cancelled)
        self.assertFalse(loop.logs[1].handle.cancelled)

        watchdog.restart()
        self.assertEqual(3, len(loop.logs))
        self.assertTrue(loop.logs[0].handle.cancelled)
        self.assertTrue(loop.logs[1].handle.cancelled)
        self.assertFalse(loop.logs[2].handle.cancelled)

        watchdog.stop()
        self.assertEqual(3, len(loop.logs))
        self.assertTrue(loop.logs[0].handle.cancelled)
        self.assertTrue(loop.logs[1].handle.cancelled)
        self.assertTrue(loop.logs[2].handle.cancelled)

    def test_watchdog_state_transition(self):
        loop = MockLoop()

        watchdog = Watchdog(10, self.fail, loop=loop)
        self.assertFalse(watchdog.started)
        self.assertTrue(watchdog.stopped)

        for _ in range(3):
            watchdog.start()
            self.assertTrue(watchdog.started)
            self.assertFalse(watchdog.stopped)

        for _ in range(3):
            watchdog.restart()
            self.assertTrue(watchdog.started)
            self.assertFalse(watchdog.stopped)

        for _ in range(3):
            watchdog.stop()
            self.assertFalse(watchdog.started)
            self.assertTrue(watchdog.stopped)

        for _ in range(3):
            watchdog.restart()
            self.assertTrue(watchdog.started)
            self.assertFalse(watchdog.stopped)


if __name__ == '__main__':
    unittest.main()
