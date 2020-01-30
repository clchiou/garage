import unittest

import dataclasses
from pathlib import Path

import g1.files
from g1.bases.assertions import ASSERT
from g1.files import locks
from g1.operations import models
from g1.operations import repos
from g1.texts import jsons

try:
    from g1.devtools.tests import filelocks
except ImportError:
    filelocks = None

from tests import fixtures


@dataclasses.dataclass
class NullDeployInstruction:
    label: str = '//foo/bar:dummy'
    version: str = '0.0.1'


@dataclasses.dataclass
class NullMetadata:
    label: str = '//foo/bar:dummy'
    version: str = '0.0.1'


class NullBundleDir(repos.AbstractBundleDir):

    deploy_instruction_type = NullDeployInstruction

    def post_init(self):
        ASSERT.predicate(self.path, Path.is_dir)


class NullOpsDir(repos.AbstractOpsDir):

    metadata_type = NullMetadata

    def install(self, bundle_dir, target_ops_dir_path):  # pylint: disable=no-self-use
        del bundle_dir, target_ops_dir_path  # Unused.
        return True

    def check_invariants(self, active_ops_dirs):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def uninstall(self):  # pylint: disable=no-self-use
        return True


class OpsDirsTest(
    fixtures.TestCaseBase,
    filelocks.Fixture if filelocks else object,
):

    DEPLOY_INSTRUCTION = NullDeployInstruction()

    def make_bundle_dir(self):
        jsons.dump_dataobject(
            self.DEPLOY_INSTRUCTION,
            self.test_bundle_dir_path / \
            models.BUNDLE_DEPLOY_INSTRUCTION_FILENAME,
        )
        return NullBundleDir(self.test_bundle_dir_path)

    def make_ops_dirs(self):
        repos.OpsDirs.init(self.test_repo_path)
        return repos.OpsDirs(
            'test',
            self.test_repo_path,
            bundle_dir_type=NullBundleDir,
            ops_dir_type=NullOpsDir,
        )

    def assert_emptiness(self, ops_dirs, active, graveyard, tmp):
        self.assertEqual(
            g1.files.is_empty_dir(ops_dirs.active_dir_path), active
        )
        self.assertEqual(
            g1.files.is_empty_dir(ops_dirs.graveyard_dir_path), graveyard
        )
        self.assertEqual(g1.files.is_empty_dir(ops_dirs.tmp_dir_path), tmp)

    def test_init(self):
        with self.assertRaises(AssertionError):
            repos.OpsDirs(
                'test',
                self.test_repo_path,
                bundle_dir_type=NullBundleDir,
                ops_dir_type=NullOpsDir,
            )
        ops_dirs = self.make_ops_dirs()
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
        self.assertTrue(ops_dirs.path.is_dir())
        self.assert_emptiness(ops_dirs, True, True, True)

    def do_install(self, ops_dirs):
        bundle_dir = self.make_bundle_dir()
        self.assertTrue(ops_dirs.install(bundle_dir.path))
        with ops_dirs.using_ops_dir(
            bundle_dir.label, bundle_dir.version
        ) as ops_dir:
            self.assertIsNotNone(ops_dir)
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
                self.DEPLOY_INSTRUCTION.label,
                self.DEPLOY_INSTRUCTION.version,
            ) as actual:
                self.assertEqual(actual, ops_dir)
        with self.using_exclusive(ops_dirs.active_dir_path):
            with self.assertRaises(locks.NotLocked):
                with ops_dirs.using_ops_dir(
                    self.DEPLOY_INSTRUCTION.label,
                    self.DEPLOY_INSTRUCTION.version,
                ):
                    pass

    def assert_using_ops_dir(self, ops_dirs, expect):
        self.assertTrue(self.check_shared(ops_dirs.active_dir_path))
        self.assertTrue(self.check_exclusive(ops_dirs.active_dir_path))
        with ops_dirs.using_ops_dir(
            self.DEPLOY_INSTRUCTION.label,
            self.DEPLOY_INSTRUCTION.version,
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

        self.assertFalse(ops_dirs.install(self.make_bundle_dir().path))
        self.assert_emptiness(ops_dirs, False, True, True)

    @unittest.skipUnless(filelocks, 'g1.tests.filelocks unavailable')
    def test_install_locked_by_other(self):
        ops_dirs = self.make_ops_dirs()
        with self.using_shared(ops_dirs.active_dir_path):
            with self.assertRaises(locks.NotLocked):
                ops_dirs.install(self.make_bundle_dir().path)

    def test_uninstall(self):
        ops_dirs = self.make_ops_dirs()
        self.assert_emptiness(ops_dirs, True, True, True)

        self.assertFalse(
            ops_dirs.uninstall(
                self.DEPLOY_INSTRUCTION.label,
                self.DEPLOY_INSTRUCTION.version,
            )
        )
        self.assert_emptiness(ops_dirs, True, True, True)

        self.do_install(ops_dirs)
        self.assert_emptiness(ops_dirs, False, True, True)

        self.assertTrue(
            ops_dirs.uninstall(
                self.DEPLOY_INSTRUCTION.label,
                self.DEPLOY_INSTRUCTION.version,
            )
        )
        self.assert_emptiness(ops_dirs, True, True, True)

    @unittest.skipUnless(filelocks, 'g1.tests.filelocks unavailable')
    def test_uninstall_lock_by_other(self):
        ops_dirs = self.make_ops_dirs()
        with self.using_shared(ops_dirs.active_dir_path):
            with self.assertRaises(locks.NotLocked):
                ops_dirs.uninstall(
                    self.DEPLOY_INSTRUCTION.label,
                    self.DEPLOY_INSTRUCTION.version,
                )

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

    def test_remove_ops_dir(self):
        ops_dirs = self.make_ops_dirs()
        ops_dir = self.do_install(ops_dirs)
        # You cannot remove an ops dir under active dir.
        with self.assertRaises(AssertionError):
            ops_dirs._remove_ops_dir(ops_dir.path)


if __name__ == '__main__':
    unittest.main()
