import unittest

import contextlib
import subprocess
import tempfile
from pathlib import Path

from g1.files import locks

try:
    from g1.devtools.tests import filelocks
except ImportError:
    filelocks = None


@unittest.skipUnless(filelocks, 'g1.tests.filelocks unavailable')
class LocksTest(
    unittest.TestCase,
    filelocks.Fixture if filelocks else object,
):

    def setUp(self):
        super().setUp()
        self._test_dir_tempdir = tempfile.TemporaryDirectory()
        self.test_dir_path = Path(self._test_dir_tempdir.name)

    def tearDown(self):
        self._test_dir_tempdir.cleanup()
        super().tearDown()

    def test_lock_not_exist(self):
        lock_path = self.test_dir_path / 'lock'
        self.assertFalse(lock_path.exists())
        with self.assertRaisesRegex(FileNotFoundError, str(lock_path)):
            locks.FileLock(lock_path)

    def test_file_lock(self):
        lock_path = self.test_dir_path / 'lock'
        lock_path.touch()
        self.assertTrue(lock_path.is_file())
        self.do_test_lock(lock_path)

    def test_dir_lock(self):
        lock_path = self.test_dir_path / 'lock'
        lock_path.mkdir()
        self.assertTrue(lock_path.is_dir())
        self.do_test_lock(lock_path)

    def do_test_lock(self, lock_path):
        lock = locks.FileLock(lock_path)
        try:

            self.assertTrue(self.check_shared(lock_path))
            self.assertTrue(self.check_exclusive(lock_path))

            lock.acquire_shared()
            try:
                self.assertTrue(self.check_shared(lock_path))
                self.assertFalse(self.check_exclusive(lock_path))
            finally:
                lock.release()

            self.assertTrue(self.check_shared(lock_path))
            self.assertTrue(self.check_exclusive(lock_path))

            lock.acquire_exclusive()
            try:
                self.assertFalse(self.check_shared(lock_path))
                self.assertFalse(self.check_exclusive(lock_path))
            finally:
                lock.release()

            self.assertTrue(self.check_shared(lock_path))
            self.assertTrue(self.check_exclusive(lock_path))

            with self.using_shared(lock_path):
                lock.acquire_shared()
                lock.release()
                with self.assertRaises(locks.NotLocked):
                    lock.acquire_exclusive()
                self.assertTrue(self.check_shared(lock_path))
                self.assertFalse(self.check_exclusive(lock_path))

            with self.using_exclusive(lock_path):
                with self.assertRaises(locks.NotLocked):
                    lock.acquire_shared()
                with self.assertRaises(locks.NotLocked):
                    lock.acquire_exclusive()
                self.assertFalse(self.check_shared(lock_path))
                self.assertFalse(self.check_exclusive(lock_path))

        finally:
            lock.close()

    def test_change_lock_type(self):
        lock_path = self.test_dir_path / 'lock'
        lock_path.touch()
        lock = locks.FileLock(lock_path)
        try:

            lock.acquire_shared()
            self.assertTrue(self.check_shared(lock_path))
            self.assertFalse(self.check_exclusive(lock_path))

            lock.acquire_exclusive()
            self.assertFalse(self.check_shared(lock_path))
            self.assertFalse(self.check_exclusive(lock_path))

            lock.acquire_shared()
            self.assertTrue(self.check_shared(lock_path))
            self.assertFalse(self.check_exclusive(lock_path))

            with self.using_shared(lock_path):
                with self.assertRaises(locks.NotLocked):
                    lock.acquire_exclusive()

        finally:
            lock.release()
            lock.close()

    def test_release_without_acquire(self):
        lock_path = self.test_dir_path / 'lock'
        lock_path.touch()
        lock = locks.FileLock(lock_path)
        lock.release()
        lock.close()

    def test_release_after_close(self):
        lock_path = self.test_dir_path / 'lock'
        lock_path.touch()
        lock = locks.FileLock(lock_path)
        lock.close()
        with self.assertRaisesRegex(AssertionError, r'expect non-None value'):
            lock.release()

    def test_remove_while_locked(self):
        lock_path = self.test_dir_path / 'lock'
        lock_path.touch()
        lock = locks.FileLock(lock_path)
        try:
            lock.acquire_shared()
            try:
                lock_path.unlink()
                self.assertFalse(lock_path.exists())
            finally:
                lock.release()
        finally:
            lock.close()
        self.assertFalse(lock_path.exists())

    def test_not_close_on_exec(self):

        @contextlib.contextmanager
        def using_dummy_proc():
            with subprocess.Popen(['cat'], close_fds=False) as proc:
                try:
                    proc.wait(0.01)  # Wait for ``cat`` to start up.
                except subprocess.TimeoutExpired:
                    pass
                try:
                    yield
                finally:
                    proc.kill()
                    proc.wait()

        lock_path = self.test_dir_path / 'lock'
        lock_path.touch()
        lock = locks.FileLock(lock_path, close_on_exec=False)
        try:

            self.assertTrue(self.check_shared(lock_path))
            self.assertTrue(self.check_exclusive(lock_path))

            lock.acquire_shared()
            self.assertTrue(self.check_shared(lock_path))
            self.assertFalse(self.check_exclusive(lock_path))

            with using_dummy_proc():
                lock.close()
                self.assertTrue(self.check_shared(lock_path))
                self.assertFalse(self.check_exclusive(lock_path))

            self.assertTrue(self.check_shared(lock_path))
            self.assertTrue(self.check_exclusive(lock_path))

        finally:
            lock.close()

    def test_acquiring_shared(self):
        lock_path = self.test_dir_path / 'lock'
        lock_path.touch()
        self.assertTrue(self.check_shared(lock_path))
        self.assertTrue(self.check_exclusive(lock_path))
        with locks.acquiring_shared(lock_path):
            self.assertTrue(self.check_shared(lock_path))
            self.assertFalse(self.check_exclusive(lock_path))
        self.assertTrue(self.check_shared(lock_path))
        self.assertTrue(self.check_exclusive(lock_path))

    def test_acquiring_exclusive(self):
        lock_path = self.test_dir_path / 'lock'
        lock_path.touch()
        self.assertTrue(self.check_shared(lock_path))
        self.assertTrue(self.check_exclusive(lock_path))
        with locks.acquiring_exclusive(lock_path):
            self.assertFalse(self.check_shared(lock_path))
            self.assertFalse(self.check_exclusive(lock_path))
        self.assertTrue(self.check_shared(lock_path))
        self.assertTrue(self.check_exclusive(lock_path))

    def test_try_acquire_exclusive(self):
        lock_path = self.test_dir_path / 'lock'
        lock_path.touch()
        lock = locks.try_acquire_exclusive(lock_path)
        try:
            self.assertIsNotNone(lock)
        finally:
            lock.release()
            lock.close()

        with self.using_shared(lock_path):
            self.assertIsNone(locks.try_acquire_exclusive(lock_path))

    def test_is_locked_by_other(self):
        self.assertFalse(locks.is_locked_by_other(self.test_dir_path))
        with self.using_shared(self.test_dir_path):
            self.assertTrue(locks.is_locked_by_other(self.test_dir_path))


if __name__ == '__main__':
    unittest.main()
