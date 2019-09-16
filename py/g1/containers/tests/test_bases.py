import unittest

import contextlib
import dataclasses
import shutil
import subprocess
import typing

from g1.containers import bases

from tests import fixtures


@dataclasses.dataclass(frozen=True)
class TestData:
    s: str
    l: typing.List[int]


class BasesTest(fixtures.TestCaseBase):

    def test_get_repo_path(self):
        self.assertEqual(
            bases.get_repo_path(),
            self.test_repo_path / bases.REPO_LAYOUT_VERSION,
        )

    def test_cmd_init(self):
        bases.cmd_init()
        self.assertTrue(self.test_repo_path.is_dir())
        path = self.test_repo_path / bases.REPO_LAYOUT_VERSION
        self.assertTrue(path.is_dir())
        self.assertEqual(path.stat().st_mode & 0o777, 0o750)
        self.assertEqual(
            sorted(p.name for p in self.test_repo_path.iterdir()),
            [bases.REPO_LAYOUT_VERSION],
        )

    def test_is_empty_dir(self):
        path = self.test_repo_path / 'some-file'
        self.assertTrue(bases.is_empty_dir(self.test_repo_path))
        self.assertFalse(bases.is_empty_dir(path))

        path.touch()
        self.assertFalse(bases.is_empty_dir(self.test_repo_path))
        self.assertFalse(bases.is_empty_dir(path))

    def test_lexists(self):
        src_path = self.test_repo_path / 'src'
        dst_path = self.test_repo_path / 'dst'

        self.assertFalse(src_path.exists())
        self.assertFalse(dst_path.exists())
        self.assertFalse(bases.lexists(src_path))
        self.assertFalse(bases.lexists(dst_path))

        src_path.symlink_to(dst_path)
        self.assertFalse(src_path.exists())
        self.assertFalse(dst_path.exists())
        self.assertTrue(bases.lexists(src_path))
        self.assertFalse(bases.lexists(dst_path))

        dst_path.touch()
        self.assertTrue(src_path.exists())
        self.assertTrue(dst_path.exists())
        self.assertTrue(bases.lexists(src_path))
        self.assertTrue(bases.lexists(dst_path))

    def test_delete_file(self):

        paths = [
            self.test_repo_path / 'dir-link',
            self.test_repo_path / 'file-link',
            self.test_repo_path / 'some-dir',
            self.test_repo_path / 'some-file',
        ]
        paths[0].symlink_to('some-dir')
        paths[1].symlink_to('some-file')
        paths[2].mkdir()
        paths[3].touch()
        for path in paths:
            with self.subTest(path):
                self.assertTrue(bases.lexists(path))
                self.assertTrue(path.exists())
                bases.delete_file(path)
                # Safe to delete non-existent files.
                self.assertFalse(bases.lexists(path))
                self.assertFalse(path.exists())
                bases.delete_file(path)

        path = self.test_repo_path / 'dangling-link'
        path.symlink_to('no-such-file')
        self.assertTrue(bases.lexists(path))
        self.assertFalse(path.exists())
        bases.delete_file(path)
        # Safe to delete non-existent files.
        self.assertFalse(bases.lexists(path))
        self.assertFalse(path.exists())
        bases.delete_file(path)

        (self.test_repo_path / 'some-dir-2').mkdir()
        (self.test_repo_path / 'dir-link-2').symlink_to('some-dir-2')
        with self.assertRaisesRegex(
            OSError, r'Cannot call rmtree on a symbolic link'
        ):
            shutil.rmtree(self.test_repo_path / 'dir-link-2')

    def test_jsonobject(self):
        path = self.test_repo_path / 'data'
        expect = TestData(s='s', l=[1, 2, 3])
        bases.write_jsonobject(expect, path)
        self.assertEqual(bases.read_jsonobject(TestData, path), expect)


class FileLockTest(fixtures.TestCaseBase):

    def test_lock_not_exist(self):
        lock_path = self.test_repo_path / 'lock'
        self.assertFalse(lock_path.exists())
        with self.assertRaisesRegex(FileNotFoundError, str(lock_path)):
            bases.FileLock(lock_path)

    def test_file_lock(self):
        lock_path = self.test_repo_path / 'lock'
        lock_path.touch()
        self.assertTrue(lock_path.is_file())
        self.do_test_lock(lock_path)

    def test_dir_lock(self):
        lock_path = self.test_repo_path / 'lock'
        lock_path.mkdir()
        self.assertTrue(lock_path.is_dir())
        self.do_test_lock(lock_path)

    def do_test_lock(self, lock_path):
        lock = bases.FileLock(lock_path)
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
                with self.assertRaises(bases.NotLocked):
                    lock.acquire_exclusive()
                self.assertTrue(self.check_shared(lock_path))
                self.assertFalse(self.check_exclusive(lock_path))

            with self.using_exclusive(lock_path):
                with self.assertRaises(bases.NotLocked):
                    lock.acquire_shared()
                with self.assertRaises(bases.NotLocked):
                    lock.acquire_exclusive()
                self.assertFalse(self.check_shared(lock_path))
                self.assertFalse(self.check_exclusive(lock_path))

        finally:
            lock.close()

    def test_change_lock_type(self):
        lock_path = self.test_repo_path / 'lock'
        lock_path.touch()
        lock = bases.FileLock(lock_path)
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
                with self.assertRaises(bases.NotLocked):
                    lock.acquire_exclusive()

        finally:
            lock.release()
            lock.close()

    def test_release_without_acquire(self):
        lock_path = self.test_repo_path / 'lock'
        lock_path.touch()
        lock = bases.FileLock(lock_path)
        lock.release()
        lock.close()

    def test_release_after_close(self):
        lock_path = self.test_repo_path / 'lock'
        lock_path.touch()
        lock = bases.FileLock(lock_path)
        lock.close()
        with self.assertRaisesRegex(AssertionError, r'expect non-None value'):
            lock.release()

    def test_remove_while_locked(self):
        lock_path = self.test_repo_path / 'lock'
        lock_path.touch()
        lock = bases.FileLock(lock_path)
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

        lock_path = self.test_repo_path / 'lock'
        lock_path.touch()
        lock = bases.FileLock(lock_path, close_on_exec=False)
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
        lock_path = self.test_repo_path / 'lock'
        lock_path.touch()
        self.assertTrue(self.check_shared(lock_path))
        self.assertTrue(self.check_exclusive(lock_path))
        with bases.acquiring_shared(lock_path):
            self.assertTrue(self.check_shared(lock_path))
            self.assertFalse(self.check_exclusive(lock_path))
        self.assertTrue(self.check_shared(lock_path))
        self.assertTrue(self.check_exclusive(lock_path))

    def test_acquiring_exclusive(self):
        lock_path = self.test_repo_path / 'lock'
        lock_path.touch()
        self.assertTrue(self.check_shared(lock_path))
        self.assertTrue(self.check_exclusive(lock_path))
        with bases.acquiring_exclusive(lock_path):
            self.assertFalse(self.check_shared(lock_path))
            self.assertFalse(self.check_exclusive(lock_path))
        self.assertTrue(self.check_shared(lock_path))
        self.assertTrue(self.check_exclusive(lock_path))

    def test_try_acquire_exclusive(self):
        lock_path = self.test_repo_path / 'lock'
        lock_path.touch()
        lock = bases.try_acquire_exclusive(lock_path)
        try:
            self.assertIsNotNone(lock)
        finally:
            lock.release()
            lock.close()

        with self.using_shared(lock_path):
            self.assertIsNone(bases.try_acquire_exclusive(lock_path))

    def test_is_locked_by_other(self):
        self.assertFalse(bases.is_locked_by_other(self.test_repo_path))
        with self.using_shared(self.test_repo_path):
            self.assertTrue(bases.is_locked_by_other(self.test_repo_path))


if __name__ == '__main__':
    unittest.main()
