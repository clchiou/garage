import unittest
import unittest.mock

import g1.files
from g1.containers import models as ctr_models
from g1.operations.cores import models
from g1.operations.cores import xar_ops_dirs
from g1.texts import jsons

from tests import fixtures


class TestCaseBase(fixtures.TestCaseBase):

    XAR_DEPLOY_INSTRUCTION = models.XarDeployInstruction(
        label='//for/bar:dummy-xar',
        version='0.0.1',
        exec_relpath='usr/local/bin/dummy-xar',
        image=ctr_models.PodConfig.Image(tag='some-tag'),
    )

    XAR_METADATA = models.XarMetadata(
        label=XAR_DEPLOY_INSTRUCTION.label,
        version=XAR_DEPLOY_INSTRUCTION.version,
        image=XAR_DEPLOY_INSTRUCTION.image,
    )

    ZIPAPP_DEPLOY_INSTRUCTION = models.XarDeployInstruction(
        label='//foo/bar:dummy-zipapp',
        version='0.0.2',
        exec_relpath=None,
        image=None,
    )

    ZIPAPP_METADATA = models.XarMetadata(
        label=ZIPAPP_DEPLOY_INSTRUCTION.label,
        version=ZIPAPP_DEPLOY_INSTRUCTION.version,
        image=ZIPAPP_DEPLOY_INSTRUCTION.image,
    )

    def setUp(self):
        super().setUp()
        self.ctr_scripts_mock = unittest.mock.patch(
            xar_ops_dirs.__name__ + '.ctr_scripts'
        ).start()

    def tearDown(self):
        unittest.mock.patch.stopall()
        super().tearDown()

    def make_xar_bundle(self):
        jsons.dump_dataobject(
            self.XAR_DEPLOY_INSTRUCTION,
            self.test_bundle_dir_path / \
            models.BUNDLE_DEPLOY_INSTRUCTION_FILENAME,
        )
        (self.test_bundle_dir_path / models.XAR_BUNDLE_IMAGE_FILENAME).touch()
        return xar_ops_dirs.XarBundleDir(self.test_bundle_dir_path)

    def make_zipapp_bundle(self):
        jsons.dump_dataobject(
            self.ZIPAPP_DEPLOY_INSTRUCTION,
            self.test_bundle_dir_path / \
            models.BUNDLE_DEPLOY_INSTRUCTION_FILENAME,
        )
        (self.test_bundle_dir_path / models.XAR_BUNDLE_ZIPAPP_FILENAME).touch()
        return xar_ops_dirs.XarBundleDir(self.test_bundle_dir_path)


class XarBundleDirTest(TestCaseBase):

    def test_xar_bundle_dir(self):
        bundle_dir = self.make_xar_bundle()
        self.assertEqual(
            bundle_dir.deploy_instruction,
            self.XAR_DEPLOY_INSTRUCTION,
        )
        self.assertEqual(
            bundle_dir.image_path,
            self.test_bundle_dir_path / models.XAR_BUNDLE_IMAGE_FILENAME,
        )
        with self.assertRaises(AssertionError):
            bundle_dir.zipapp_path  # pylint: disable=pointless-statement

    def test_zipapp_bundle_dir(self):
        bundle_dir = self.make_zipapp_bundle()
        self.assertEqual(
            bundle_dir.deploy_instruction,
            self.ZIPAPP_DEPLOY_INSTRUCTION,
        )
        self.assertEqual(
            bundle_dir.zipapp_path,
            self.test_bundle_dir_path / models.XAR_BUNDLE_ZIPAPP_FILENAME,
        )
        with self.assertRaises(AssertionError):
            bundle_dir.image_path  # pylint: disable=pointless-statement


class XarOpsDirTest(TestCaseBase):

    def make_ops_dir(self):
        return xar_ops_dirs.XarOpsDir(self.test_ops_dir_path)

    def test_install_xar(self):
        bundle_dir = self.make_xar_bundle()
        ops_dir = self.make_ops_dir()

        ops_dir.install(bundle_dir, None)
        self.assertEqual(self.list_dir(self.test_ops_dir_path), ['metadata'])
        self.ctr_scripts_mock.ctr_import_image.assert_called_once_with(
            bundle_dir.image_path,
        )
        self.ctr_scripts_mock.ctr_install_xar.assert_called_once_with(
            self.XAR_DEPLOY_INSTRUCTION.name,
            self.XAR_DEPLOY_INSTRUCTION.exec_relpath,
            self.XAR_DEPLOY_INSTRUCTION.image,
        )

        self.assertTrue(ops_dir.uninstall())
        self.assertTrue(g1.files.is_empty_dir(self.test_ops_dir_path))
        self.ctr_scripts_mock.ctr_uninstall_xar.assert_called_once_with(
            self.XAR_METADATA.name,
        )
        self.ctr_scripts_mock.ctr_remove_image.assert_called_once_with(
            self.XAR_METADATA.image,
        )

        self.assertFalse(ops_dir.uninstall())

    def test_install_zipapp(self):
        self.assertTrue(g1.files.is_empty_dir(self.test_zipapp_dir_path))
        bundle_dir = self.make_zipapp_bundle()
        ops_dir = self.make_ops_dir()

        ops_dir.install(bundle_dir, None)
        self.assertEqual(self.list_dir(self.test_ops_dir_path), ['metadata'])
        self.assertEqual(
            self.list_dir(self.test_zipapp_dir_path),
            [self.ZIPAPP_DEPLOY_INSTRUCTION.name],
        )

        self.assertTrue(ops_dir.uninstall())
        self.assertTrue(g1.files.is_empty_dir(self.test_ops_dir_path))
        self.assertTrue(g1.files.is_empty_dir(self.test_zipapp_dir_path))

        self.assertFalse(ops_dir.uninstall())


class InvariantsTest(TestCaseBase):

    XAR_DEPLOY_INSTRUCTION_2 = models.XarDeployInstruction(
        label='//spam/egg:dummy-xar',
        version='0.0.2',
        exec_relpath='usr/local/bin/dummy-xar',
        image=ctr_models.PodConfig.Image(tag='some-tag'),
    )

    def setUp(self):
        super().setUp()
        (self.test_repo_path / 'v1' / 'xars').mkdir(parents=True)
        xar_ops_dirs.init()

    def test_check_invariants(self):
        b1_path = self.test_bundle_dir_path / 'bundle-1'
        b2_path = self.test_bundle_dir_path / 'bundle-2'
        for path, deploy_instruction in (
            (b1_path, self.XAR_DEPLOY_INSTRUCTION),
            (b2_path, self.XAR_DEPLOY_INSTRUCTION_2),
        ):
            path.mkdir()
            jsons.dump_dataobject(
                deploy_instruction,
                path / models.BUNDLE_DEPLOY_INSTRUCTION_FILENAME,
            )
            (path / models.XAR_BUNDLE_IMAGE_FILENAME).touch()
        ops_dirs = xar_ops_dirs.make_ops_dirs()
        with ops_dirs.listing_ops_dirs() as actual:
            self.assertEqual(actual, [])
        self.assertTrue(ops_dirs.install(b1_path))
        with ops_dirs.listing_ops_dirs() as actual:
            self.assertEqual(len(actual), 1)
            self.assertEqual(actual[0].metadata, self.XAR_METADATA)
        with self.assertRaisesRegex(
            AssertionError,
            r'expect unique xar label name:',
        ):
            ops_dirs.install(b2_path)
        with ops_dirs.listing_ops_dirs() as actual:
            self.assertEqual(len(actual), 1)
            self.assertEqual(actual[0].metadata, self.XAR_METADATA)


if __name__ == '__main__':
    unittest.main()
