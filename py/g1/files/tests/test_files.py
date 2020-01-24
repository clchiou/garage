import unittest

import shutil
import tempfile
from pathlib import Path

import g1.files


class FilesTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self._test_dir_tempdir = tempfile.TemporaryDirectory()
        self.test_dir_path = Path(self._test_dir_tempdir.name)

    def tearDown(self):
        self._test_dir_tempdir.cleanup()
        super().tearDown()

    def test_is_empty_dir(self):
        path = self.test_dir_path / 'some-file'
        self.assertTrue(g1.files.is_empty_dir(self.test_dir_path))
        self.assertFalse(g1.files.is_empty_dir(path))

        path.touch()
        self.assertFalse(g1.files.is_empty_dir(self.test_dir_path))
        self.assertFalse(g1.files.is_empty_dir(path))

    def test_lexists(self):
        src_path = self.test_dir_path / 'src'
        dst_path = self.test_dir_path / 'dst'

        self.assertFalse(src_path.exists())
        self.assertFalse(dst_path.exists())
        self.assertFalse(g1.files.lexists(src_path))
        self.assertFalse(g1.files.lexists(dst_path))

        src_path.symlink_to(dst_path)
        self.assertFalse(src_path.exists())
        self.assertFalse(dst_path.exists())
        self.assertTrue(g1.files.lexists(src_path))
        self.assertFalse(g1.files.lexists(dst_path))

        dst_path.touch()
        self.assertTrue(src_path.exists())
        self.assertTrue(dst_path.exists())
        self.assertTrue(g1.files.lexists(src_path))
        self.assertTrue(g1.files.lexists(dst_path))

    def test_remove(self):

        paths = [
            self.test_dir_path / 'dir-link',
            self.test_dir_path / 'file-link',
            self.test_dir_path / 'some-dir',
            self.test_dir_path / 'some-file',
        ]
        paths[0].symlink_to('some-dir')
        paths[1].symlink_to('some-file')
        paths[2].mkdir()
        paths[3].touch()
        for path in paths:
            with self.subTest(path):
                self.assertTrue(g1.files.lexists(path))
                self.assertTrue(path.exists())
                g1.files.remove(path)
                # Safe to delete non-existent files.
                self.assertFalse(g1.files.lexists(path))
                self.assertFalse(path.exists())
                g1.files.remove(path)

        path = self.test_dir_path / 'dangling-link'
        path.symlink_to('no-such-file')
        self.assertTrue(g1.files.lexists(path))
        self.assertFalse(path.exists())
        g1.files.remove(path)
        # Safe to delete non-existent files.
        self.assertFalse(g1.files.lexists(path))
        self.assertFalse(path.exists())
        g1.files.remove(path)

        (self.test_dir_path / 'some-dir-2').mkdir()
        (self.test_dir_path / 'dir-link-2').symlink_to('some-dir-2')
        with self.assertRaisesRegex(
            OSError, r'Cannot call rmtree on a symbolic link'
        ):
            shutil.rmtree(self.test_dir_path / 'dir-link-2')


if __name__ == '__main__':
    unittest.main()
