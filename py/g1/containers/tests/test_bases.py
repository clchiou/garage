import unittest

import shutil

from g1.containers import bases

from tests import fixtures


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


if __name__ == '__main__':
    unittest.main()
