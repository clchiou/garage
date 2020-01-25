import unittest

from pathlib import Path

import g1.files
from g1.bases.assertions import ASSERT
from g1.files import locks
from g1.operations import repos

try:
    from g1.devtools.tests import filelocks
except ImportError:
    filelocks = None

from tests import fixtures


class NullBundleDir(repos.BundleDirInterface):

    name = 'dummy'
    version = '0.0.1'

    def __init__(self, path):
        self.path_unchecked = path

    def check(self):
        ASSERT.predicate(self.path_unchecked, Path.is_dir)

    def install(self):  # pylint: disable=no-self-use
        return True

    def uninstall(self):  # pylint: disable=no-self-use
        return True


class NullOpsDir(repos.OpsDirInterface):

    def __init__(self, path):
        self.path_unchecked = path

    def init(self):
        self.path_unchecked.mkdir(exist_ok=True)

    def check(self):
        ASSERT.predicate(self.path_unchecked, Path.is_dir)

    def cleanup(self):
        pass

    def check_invariants(self, ops_dirs):
        pass

    @staticmethod
    def get_ops_dir_name(name, version):
        return '%s-%s' % (name, version)

    def init_from_bundle_dir(self, bundle_dir):
        pass

    def activate(self):
        pass

    def deactivate(self):
        pass

    def uninstall(self):  # pylint: disable=no-self-use
        return True


class OpsDirsTest(
    fixtures.TestCaseBase,
    filelocks.Fixture if filelocks else object,
):

    def make_bundle_dir(self):
        self.test_bundle_dir_path.mkdir(exist_ok=True)
        return NullBundleDir(self.test_bundle_dir_path)

    def make_ops_dirs(self):
        ops_dirs = repos.OpsDirs(
            'test',
            self.test_repo_path,
            bundle_dir_type=NullBundleDir,
            ops_dir_type=NullOpsDir,
        )
        ops_dirs.init()
        return ops_dirs

    def test_init(self):
        ops_dirs = repos.OpsDirs(
            'test',
            self.test_repo_path,
            bundle_dir_type=NullBundleDir,
            ops_dir_type=NullOpsDir,
        )
        with self.assertRaises(AssertionError):
            ops_dirs.check()
        ops_dirs.init()
        ops_dirs.check()
        self.assertEqual(ops_dirs.path, self.test_repo_path)
        self.assertEqual(
            ops_dirs.active_dir_path,
            self.test_repo_path / 'active',
        )
        self.assertEqual(
            ops_dirs.graveyard_dir_path,
            self.test_repo_path / 'graveyard',
        )
        self.assertEqual(
            ops_dirs.tmp_dir_path,
            self.test_repo_path / 'tmp',
        )
        self.assertTrue(ops_dirs.path.is_dir())  # pylint: disable=no-member
        self.assert_emptiness(ops_dirs, True, True, True)

    def assert_emptiness(self, ops_dirs, active, graveyard, tmp):
        self.assertEqual(
            g1.files.is_empty_dir(ops_dirs.active_dir_path), active
        )
        self.assertEqual(
            g1.files.is_empty_dir(ops_dirs.graveyard_dir_path), graveyard
        )
        self.assertEqual(g1.files.is_empty_dir(ops_dirs.tmp_dir_path), tmp)

    def do_install(self, ops_dirs):
        bundle_dir = self.make_bundle_dir()
        self.assertTrue(ops_dirs.install(bundle_dir))
        with ops_dirs.using_ops_dir(
            bundle_dir.name, bundle_dir.version
        ) as ops_dir:
            self.assertIsNotNone(ops_dir)
        # You cannot remove an ops dir under active dir.
        with self.assertRaises(AssertionError):
            ops_dir.remove()
        return ops_dir

    @unittest.skipUnless(filelocks, 'g1.tests.filelocks unavailable')
    def test_listing_ops_dirs(self):
        ops_dirs = self.make_ops_dirs()
        self.assert_listing_ops_dirs(ops_dirs, [])
        ops_dir = self.do_install(ops_dirs)
        self.assert_listing_ops_dirs(ops_dirs, [ops_dir])

        with self.using_shared(ops_dirs.active_dir_path):
            with ops_dirs.listing_ops_dirs() as actual:
                self.assertEqual(actual, [ops_dir])
        with self.using_exclusive(ops_dirs.active_dir_path):
            with self.assertRaises(locks.NotLocked):
                with ops_dirs.listing_ops_dirs():
                    pass

    def assert_listing_ops_dirs(self, ops_dirs, expect):
        self.assertTrue(self.check_shared(ops_dirs.active_dir_path))
        self.assertTrue(self.check_exclusive(ops_dirs.active_dir_path))
        with ops_dirs.listing_ops_dirs() as actual:
            self.assertTrue(self.check_shared(ops_dirs.active_dir_path))
            self.assertFalse(self.check_exclusive(ops_dirs.active_dir_path))
            self.assertEqual(actual, expect)
        self.assertTrue(self.check_shared(ops_dirs.active_dir_path))
        self.assertTrue(self.check_exclusive(ops_dirs.active_dir_path))

    @unittest.skipUnless(filelocks, 'g1.tests.filelocks unavailable')
    def test_using_ops_dir(self):
        ops_dirs = self.make_ops_dirs()
        self.assert_using_ops_dir(ops_dirs, None)
        ops_dir = self.do_install(ops_dirs)
        self.assert_using_ops_dir(ops_dirs, ops_dir)

        with self.using_shared(ops_dirs.active_dir_path):
            with ops_dirs.using_ops_dir(
                NullBundleDir.name,
                NullBundleDir.version,
            ) as actual:
                self.assertEqual(actual, ops_dir)
        with self.using_exclusive(ops_dirs.active_dir_path):
            with self.assertRaises(locks.NotLocked):
                with ops_dirs.using_ops_dir(
                    NullBundleDir.name,
                    NullBundleDir.version,
                ):
                    pass

    def assert_using_ops_dir(self, ops_dirs, expect):
        self.assertTrue(self.check_shared(ops_dirs.active_dir_path))
        self.assertTrue(self.check_exclusive(ops_dirs.active_dir_path))
        with ops_dirs.using_ops_dir(
            NullBundleDir.name,
            NullBundleDir.version,
        ) as actual:
            self.assertTrue(self.check_shared(ops_dirs.active_dir_path))
            self.assertTrue(self.check_exclusive(ops_dirs.active_dir_path))
            self.assertEqual(actual, expect)
        self.assertTrue(self.check_shared(ops_dirs.active_dir_path))
        self.assertTrue(self.check_exclusive(ops_dirs.active_dir_path))

    def test_install(self):
        ops_dirs = self.make_ops_dirs()
        self.assert_emptiness(ops_dirs, True, True, True)

        self.do_install(ops_dirs)
        self.assert_emptiness(ops_dirs, False, True, True)

        self.assertFalse(ops_dirs.install(self.make_bundle_dir()))
        self.assert_emptiness(ops_dirs, False, True, True)

    @unittest.skipUnless(filelocks, 'g1.tests.filelocks unavailable')
    def test_install_locked_by_other(self):
        ops_dirs = self.make_ops_dirs()
        with self.using_shared(ops_dirs.active_dir_path):
            with self.assertRaises(locks.NotLocked):
                ops_dirs.install(self.make_bundle_dir())

    @unittest.skipUnless(filelocks, 'g1.tests.filelocks unavailable')
    def test_make_tmp_ops_dir(self):
        ops_dirs = self.make_ops_dirs()
        tmp_ops_dir = ops_dirs._make_tmp_ops_dir()
        self.assertEqual(tmp_ops_dir.path.parent, ops_dirs.tmp_dir_path)

        with self.using_shared(ops_dirs.tmp_dir_path):
            with self.assertRaises(locks.NotLocked):
                ops_dirs._make_tmp_ops_dir()

    def test_uninstall(self):
        ops_dirs = self.make_ops_dirs()
        self.assert_emptiness(ops_dirs, True, True, True)

        self.assertFalse(
            ops_dirs.uninstall(NullBundleDir.name, NullBundleDir.version)
        )
        self.assert_emptiness(ops_dirs, True, True, True)

        self.do_install(ops_dirs)
        self.assert_emptiness(ops_dirs, False, True, True)

        self.assertTrue(
            ops_dirs.uninstall(NullBundleDir.name, NullBundleDir.version)
        )
        self.assert_emptiness(ops_dirs, True, True, True)

    @unittest.skipUnless(filelocks, 'g1.tests.filelocks unavailable')
    def test_uninstall_lock_by_other(self):
        ops_dirs = self.make_ops_dirs()
        with self.using_shared(ops_dirs.active_dir_path):
            with self.assertRaises(locks.NotLocked):
                ops_dirs.uninstall(NullBundleDir.name, NullBundleDir.version)

    def test_move_to_graveyard(self):
        ops_dirs = self.make_ops_dirs()
        self.assert_emptiness(ops_dirs, True, True, True)
        ops_dir = self.do_install(ops_dirs)
        self.assert_emptiness(ops_dirs, False, True, True)
        ops_dirs._move_to_graveyard(ops_dir.path)
        self.assert_emptiness(ops_dirs, True, False, True)

    def test_cleanup(self):
        ops_dirs = self.make_ops_dirs()
        for top_dir_path in (
            ops_dirs.graveyard_dir_path,
            ops_dirs.tmp_dir_path,
        ):
            (top_dir_path / 'junk-file').touch()
            (top_dir_path / 'junk-dir').mkdir()
        self.assert_emptiness(ops_dirs, True, False, False)
        ops_dirs.cleanup()
        self.assert_emptiness(ops_dirs, True, True, True)

    @unittest.skipUnless(filelocks, 'g1.tests.filelocks unavailable')
    def test_cleanup_lock_by_other(self):
        ops_dirs = self.make_ops_dirs()
        with self.using_shared(ops_dirs.graveyard_dir_path):
            with self.assertRaises(locks.NotLocked):
                ops_dirs.cleanup()
        with self.using_shared(ops_dirs.tmp_dir_path):
            with self.assertRaises(locks.NotLocked):
                ops_dirs.cleanup()


if __name__ == '__main__':
    unittest.main()
