import unittest

import threading

from g1.threads import locks


class ReadWriteLockTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.rwlock = locks.ReadWriteLock()

    def assert_state(self, num_readers, num_writers):
        self.assertEqual(self.rwlock._num_readers, num_readers)
        self.assertEqual(self.rwlock._num_writers, num_writers)

    def test_read_lock(self):
        self.assert_state(0, 0)

        self.assertTrue(self.rwlock.reader_acquire(timeout=0.01))
        self.assert_state(1, 0)

        self.assertTrue(self.rwlock.reader_acquire(timeout=0.01))
        self.assert_state(2, 0)

        self.assertFalse(self.rwlock.writer_acquire(timeout=0.01))
        self.assert_state(2, 0)

        self.rwlock.reader_release()
        self.rwlock.reader_release()
        self.assert_state(0, 0)

    def test_write_lock(self):
        self.assert_state(0, 0)

        self.assertTrue(self.rwlock.writer_acquire(timeout=0.01))
        self.assert_state(0, 1)

        self.assertFalse(self.rwlock.reader_acquire(timeout=0.01))
        self.assert_state(0, 1)

        self.assertFalse(self.rwlock.writer_acquire(timeout=0.01))
        self.assert_state(0, 1)

        self.rwlock.writer_release()
        self.assert_state(0, 0)

    def start_reader_thread(self, event):
        thread = threading.Thread(
            target=acquire_then_set,
            args=(self.rwlock.reader_acquire, event),
            daemon=True,
        )
        thread.start()

    def start_writer_thread(self, event):
        thread = threading.Thread(
            target=acquire_then_set,
            args=(self.rwlock.writer_acquire, event),
            daemon=True,
        )
        thread.start()

    def test_reader_notify_writers(self):
        self.rwlock.reader_acquire()

        event1 = threading.Event()
        event2 = threading.Event()
        event3 = threading.Event()
        self.start_writer_thread(event1)
        self.start_writer_thread(event2)
        self.start_writer_thread(event3)
        self.assertFalse(event1.wait(0.01))
        self.assertFalse(event2.wait(0.01))
        self.assertFalse(event3.wait(0.01))

        self.rwlock.reader_release()
        self.assertEqual(
            sorted([
                event1.wait(0.01),
                event2.wait(0.01),
                event3.wait(0.01),
            ]),
            [False, False, True],
        )

    def test_writer_notify_readers(self):
        self.rwlock.writer_acquire()

        event1 = threading.Event()
        event2 = threading.Event()
        self.start_reader_thread(event1)
        self.start_reader_thread(event2)
        self.assertFalse(event1.wait(0.01))
        self.assertFalse(event2.wait(0.01))

        self.rwlock.writer_release()
        self.assertTrue(event1.wait(0.01))
        self.assertTrue(event2.wait(0.01))

    def test_writer_notify_writers(self):
        self.rwlock.writer_acquire()

        event1 = threading.Event()
        event2 = threading.Event()
        event3 = threading.Event()
        self.start_writer_thread(event1)
        self.start_writer_thread(event2)
        self.start_writer_thread(event3)
        self.assertFalse(event1.wait(0.01))
        self.assertFalse(event2.wait(0.01))
        self.assertFalse(event3.wait(0.01))

        self.rwlock.writer_release()
        self.assertEqual(
            sorted([
                event1.wait(0.01),
                event2.wait(0.01),
                event3.wait(0.01),
            ]),
            [False, False, True],
        )

    def test_writer_notify_readers_and_writers(self):
        self.rwlock.writer_acquire()

        event1 = threading.Event()
        event2 = threading.Event()
        event3 = threading.Event()
        event4 = threading.Event()
        event5 = threading.Event()
        self.start_reader_thread(event1)
        self.start_reader_thread(event2)
        self.start_writer_thread(event3)
        self.start_writer_thread(event4)
        self.start_writer_thread(event5)
        self.assertFalse(event1.wait(0.01))
        self.assertFalse(event2.wait(0.01))
        self.assertFalse(event3.wait(0.01))
        self.assertFalse(event4.wait(0.01))
        self.assertFalse(event5.wait(0.01))

        self.rwlock.writer_release()
        self.assertIn(
            (
                [
                    event1.wait(0.01),
                    event2.wait(0.01),
                ],
                sorted([
                    event3.wait(0.01),
                    event4.wait(0.01),
                    event5.wait(0.01),
                ]),
            ),
            [
                ([True, True], [False, False, False]),
                ([False, False], [False, False, True]),
            ],
        )


def acquire_then_set(acquire, event):
    acquire()
    event.set()


if __name__ == '__main__':
    unittest.main()
