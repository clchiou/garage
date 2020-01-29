import unittest
import unittest.mock

import dataclasses
from pathlib import Path

import g1.files
from g1.containers import models as ctr_models
from g1.operations import models
from g1.operations import pod_ops_dirs
from g1.texts import jsons

from tests import fixtures


class TestCaseBase(fixtures.TestCaseBase):

    DEPLOY_INSTRUCTION = models.PodDeployInstruction(
        label='//foo/bar:dummy',
        pod_config_template=ctr_models.PodConfig(
            name='dummy',
            version='0.0.1',
            apps=[],
            images=[
                ctr_models.PodConfig.Image(
                    name='some-image',
                    version='0.0.2',
                ),
            ],
            mounts=[
                ctr_models.PodConfig.Mount(
                    source='',
                    target='/tmp',
                    read_only=False,
                ),
            ],
        ),
        volumes=[
            models.PodDeployInstruction.Volume(
                label='//foo/bar:some-volume',
                version='0.0.3',
                target='/some/where',
            ),
        ],
    )

    BUNDLE_IMAGE_RELPATH = (
        Path(models.POD_BUNDLE_IMAGES_DIR_NAME) / \
        'some-image' /
        models.POD_BUNDLE_IMAGE_FILENAME
    )

    BUNDLE_VOLUME_RELPATH = (
        Path(models.POD_BUNDLE_VOLUMES_DIR_NAME) / \
        'some-volume' /
        models.POD_BUNDLE_VOLUME_FILENAME
    )

    def setUp(self):
        super().setUp()
        self.ctr_scripts_mock = unittest.mock.patch(
            pod_ops_dirs.__name__ + '.ctr_scripts'
        ).start()
        self.scripts_mock = unittest.mock.patch(
            pod_ops_dirs.__name__ + '.scripts'
        ).start()

    def tearDown(self):
        unittest.mock.patch.stopall()
        super().tearDown()

    def make_bundle_dir(self):
        self.test_bundle_dir_path.mkdir()
        jsons.dump_dataobject(
            self.DEPLOY_INSTRUCTION,
            self.test_bundle_dir_path / \
            models.BUNDLE_DEPLOY_INSTRUCTION_FILENAME,
        )
        for path in (
            self.test_bundle_dir_path / self.BUNDLE_IMAGE_RELPATH,
            self.test_bundle_dir_path / self.BUNDLE_VOLUME_RELPATH,
        ):
            path.parent.mkdir(parents=True)
            path.touch()
        bundle_dir = pod_ops_dirs.PodBundleDir(self.test_bundle_dir_path)
        bundle_dir.check()
        return bundle_dir


class PodBundleDirTest(TestCaseBase):

    def test_bundle_dir(self):
        bundle_dir = self.make_bundle_dir()
        self.assertEqual(bundle_dir.label, '//foo/bar:dummy')
        self.assertEqual(bundle_dir.version, '0.0.1')

        self.assertTrue(bundle_dir.install())
        self.ctr_scripts_mock.ctr_import_image.assert_called_once_with(
            self.test_bundle_dir_path / self.BUNDLE_IMAGE_RELPATH,
        )

        self.assertTrue(bundle_dir.uninstall())
        self.ctr_scripts_mock.ctr_remove_image.assert_called_once_with(
            self.DEPLOY_INSTRUCTION.images[0],
        )

    def test_invalid_bundle_dir(self):
        self.test_bundle_dir_path.mkdir()
        bundle_dir = pod_ops_dirs.PodBundleDir(self.test_bundle_dir_path)
        with self.assertRaises(AssertionError):
            bundle_dir.check()
        jsons.dump_dataobject(
            self.DEPLOY_INSTRUCTION,
            self.test_bundle_dir_path / \
            models.BUNDLE_DEPLOY_INSTRUCTION_FILENAME,
        )
        with self.assertRaises(AssertionError):
            bundle_dir.check()


class PodOpsDirTest(TestCaseBase):

    def make_ops_dir(self, bundle_dir):
        ops_dir = pod_ops_dirs.PodOpsDir(self.test_ops_dir_path)
        ops_dir.init()
        ops_dir.check()
        ops_dir.init_from_bundle_dir(bundle_dir, ops_dir.path_unchecked)
        return ops_dir

    def test_cleanup(self):
        ops_dir = self.make_ops_dir(self.make_bundle_dir())
        self.assertFalse(g1.files.is_empty_dir(self.test_ops_dir_path))
        ops_dir.cleanup()
        self.assertTrue(g1.files.is_empty_dir(self.test_ops_dir_path))

    def test_check_invariants(self):
        ops_dir = self.make_ops_dir(self.make_bundle_dir())
        with self.assertRaisesRegex(AssertionError, r'expect unique pod id:'):
            ops_dir.check_invariants([ops_dir])

    def test_init_from_bundle_dir(self):
        self.make_ops_dir(self.make_bundle_dir())
        self.assertEqual(
            self.list_dir(self.test_ops_dir_path),
            ['metadata', 'volumes'],
        )
        self.assertEqual(
            self.list_dir(self.test_ops_dir_path / 'volumes'),
            ['some-volume'],
        )
        # It's empty because we are not really extracting an archive
        # into it.
        self.assertTrue(
            g1.files.is_empty_dir(
                self.test_ops_dir_path / 'volumes' / 'some-volume'
            )
        )
        metadata = jsons.load_dataobject(
            models.PodMetadata,
            self.test_ops_dir_path / 'metadata',
        )
        self.assertEqual(metadata.label, self.DEPLOY_INSTRUCTION.label)
        ctr_models.validate_pod_id(metadata.pod_id)
        self.assertEqual(
            metadata.pod_config,
            dataclasses.replace(
                self.DEPLOY_INSTRUCTION.pod_config_template,
                mounts=[
                    self.DEPLOY_INSTRUCTION.pod_config_template.mounts[0],
                    ctr_models.PodConfig.Mount(
                        source=str(
                            self.test_ops_dir_path / 'volumes' / 'some-volume'
                        ),
                        target='/some/where',
                    ),
                ],
            )
        )

    def test_uninstall(self):
        bundle_dir = self.make_bundle_dir()
        ops_dir = self.make_ops_dir(bundle_dir)
        bundle_dir.install()
        ops_dir.uninstall()
        self.ctr_scripts_mock.ctr_remove_image.assert_called_once_with(
            self.DEPLOY_INSTRUCTION.images[0],
        )


if __name__ == '__main__':
    unittest.main()
