import unittest
import unittest.mock

from pathlib import Path

import g1.files
from g1.containers import models as ctr_models
from g1.operations.cores import envs
from g1.operations.cores import models
from g1.operations.cores import pod_ops_dirs
from g1.operations.cores import tokens
from g1.texts import jsons

from tests import fixtures


class PodOpsDirTest(fixtures.TestCaseBase):

    POD_ID = '00000000-0000-0000-0000-000000000001'
    UNIT_1 = models.PodDeployInstruction.SystemdUnitGroup.Unit(
        name='foo.service',
        content='',
    )
    UNIT_2 = models.PodDeployInstruction.SystemdUnitGroup.Unit(
        name='bar.service',
        content='',
        auto_start=False,
    )
    GROUP = models.PodDeployInstruction.SystemdUnitGroup(
        units=[UNIT_1, UNIT_2],
    )
    CONFIG_1 = models.PodMetadata.SystemdUnitConfig(
        pod_id=POD_ID,
        name='foo.service',
    )
    CONFIG_2 = models.PodMetadata.SystemdUnitConfig(
        pod_id=POD_ID,
        name='bar.service',
        auto_start=False,
    )

    DEPLOY_INSTRUCTION = models.PodDeployInstruction(
        label='//foo/bar:dummy',
        pod_config_template=ctr_models.PodConfig(
            name='dummy',
            version='0.0.1',
            apps=[
                ctr_models.PodConfig.App(
                    name='foo',
                    exec=['echo', 'hello', 'world'],
                ),
            ],
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
        systemd_unit_groups=[
            GROUP,
        ],
        token_names={
            'port_1': 'ops_free_port',
            'port_2': 'ops_free_port',
        },
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
        self.systemds_mock = unittest.mock.patch(
            pod_ops_dirs.__name__ + '.systemds'
        ).start()
        mock = unittest.mock.patch(
            pod_ops_dirs.__name__ + '.ctr_models.generate_pod_id'
        ).start()
        # It should only be called once.
        mock.side_effect = [self.POD_ID]
        envs.init()
        envs.save({'ops_database_url': 'tcp://127.0.0.1:2390'})
        tokens.init()
        with tokens.make_tokens_database().writing() as active_tokens:
            active_tokens.add_definition(
                'ops_free_port',
                tokens.Tokens.Definition(kind='values', args=['8001', '8002']),
            )

    def tearDown(self):
        unittest.mock.patch.stopall()
        super().tearDown()

    def make_bundle_dir(self):
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
        return pod_ops_dirs.PodBundleDir(self.test_bundle_dir_path)

    def make_ops_dir(self):
        return pod_ops_dirs.PodOpsDir(self.test_ops_dir_path)

    def test_check_invariants(self):
        bundle_dir = self.make_bundle_dir()
        ops_dir = self.make_ops_dir()
        ops_dir.install(bundle_dir, ops_dir.path)
        with self.assertRaisesRegex(AssertionError, r'expect x.isdisjoint'):
            ops_dir.check_invariants([ops_dir])

    def test_install(self):
        bundle_dir = self.make_bundle_dir()
        ops_dir = self.make_ops_dir()

        # Test install.
        self.assertTrue(ops_dir.install(bundle_dir, ops_dir.path))
        # Check ops dir structure.
        self.assertEqual(
            self.list_dir(self.test_ops_dir_path),
            ['metadata', 'refs', 'volumes'],
        )
        self.assertEqual(
            self.list_dir(self.test_ops_dir_path / 'volumes'),
            ['some-volume'],
        )
        # Check metadata.
        metadata = jsons.load_dataobject(
            models.PodMetadata,
            self.test_ops_dir_path / 'metadata',
        )
        self.assertEqual(metadata.label, self.DEPLOY_INSTRUCTION.label)
        self.assertEqual(metadata.version, self.DEPLOY_INSTRUCTION.version)
        self.assertEqual(metadata.images, self.DEPLOY_INSTRUCTION.images)
        self.assertEqual(
            metadata.systemd_unit_configs,
            [self.CONFIG_1, self.CONFIG_2],
        )
        # Check volumes.
        self.scripts_mock.tar_extract.assert_called_once()
        # Check images.
        self.ctr_scripts_mock.ctr_import_image.assert_called_once_with(
            self.test_bundle_dir_path / self.BUNDLE_IMAGE_RELPATH,
        )
        # Check pods.
        self.ctr_scripts_mock.ctr_prepare_pod.assert_called_once_with(
            self.POD_ID, unittest.mock.ANY
        )
        self.ctr_scripts_mock.ctr_add_ref_to_pod.assert_called_once_with(
            self.POD_ID,
            self.test_ops_dir_path / 'refs' / self.POD_ID,
        )
        # Check systemd units.
        self.systemds_mock.install.assert_has_calls([
            unittest.mock.call(
                self.CONFIG_1,
                ops_dir.metadata,
                self.GROUP,
                self.UNIT_1,
                {
                    'ops_database_url': 'tcp://127.0.0.1:2390',
                },
                {
                    'port_1': '8001',
                    'port_2': '8002',
                },
            ),
            unittest.mock.call(
                self.CONFIG_2,
                ops_dir.metadata,
                self.GROUP,
                self.UNIT_2,
                {
                    'ops_database_url': 'tcp://127.0.0.1:2390',
                },
                {
                    'port_1': '8001',
                    'port_2': '8002',
                },
            ),
        ])
        self.systemds_mock.daemon_reload.assert_called_once()

        # Test uninstall.
        self.systemds_mock.daemon_reload.reset_mock()
        self.assertTrue(ops_dir.uninstall())
        self.systemds_mock.uninstall.assert_has_calls([
            unittest.mock.call(self.CONFIG_1),
            unittest.mock.call(self.CONFIG_2),
        ])
        self.systemds_mock.daemon_reload.assert_called_once()
        self.ctr_scripts_mock.ctr_remove_pod.assert_called_once_with(
            self.POD_ID
        )
        self.ctr_scripts_mock.ctr_remove_image.assert_called_once_with(
            self.DEPLOY_INSTRUCTION.images[0],
        )
        self.assertTrue(g1.files.is_empty_dir(self.test_ops_dir_path))

        self.assertFalse(ops_dir.uninstall())

    def test_start_invalid_args(self):
        ops_dir = self.make_ops_dir()
        with self.assertRaisesRegex(AssertionError, r'expect not all'):
            ops_dir.start(unit_names=[], all_units=True)
        with self.assertRaisesRegex(AssertionError, r'expect not all'):
            ops_dir.start(unit_names=[self.UNIT_1.name], all_units=True)

    def test_start_default(self):
        bundle_dir = self.make_bundle_dir()
        ops_dir = self.make_ops_dir()
        ops_dir.install(bundle_dir, ops_dir.path)
        ops_dir.start()
        self.systemds_mock.activate.assert_called_once_with(self.CONFIG_1)
        self.systemds_mock.deactivate.assert_not_called()

    def test_start_all(self):
        bundle_dir = self.make_bundle_dir()
        ops_dir = self.make_ops_dir()
        ops_dir.install(bundle_dir, ops_dir.path)
        ops_dir.start(all_units=True)
        self.systemds_mock.activate.assert_has_calls([
            unittest.mock.call(self.CONFIG_1),
            unittest.mock.call(self.CONFIG_2),
        ])
        self.systemds_mock.deactivate.assert_not_called()

    def test_start_unit_names(self):
        bundle_dir = self.make_bundle_dir()
        ops_dir = self.make_ops_dir()
        ops_dir.install(bundle_dir, ops_dir.path)
        ops_dir.start(unit_names=['bar.service'])
        self.systemds_mock.activate.assert_called_once_with(self.CONFIG_2)
        self.systemds_mock.deactivate.assert_not_called()

    def test_stop(self):
        bundle_dir = self.make_bundle_dir()
        ops_dir = self.make_ops_dir()
        ops_dir.install(bundle_dir, ops_dir.path)
        ops_dir.stop()
        self.systemds_mock.activate.assert_not_called()
        self.systemds_mock.deactivate.assert_has_calls([
            unittest.mock.call(self.CONFIG_1),
            unittest.mock.call(self.CONFIG_2),
        ])


class PodConfigTest(unittest.TestCase):

    POD_CONFIG_TEMPLATE = ctr_models.PodConfig(
        name='dummy',
        version='0.0.1',
        apps=[
            ctr_models.PodConfig.App(
                name='foo',
                exec=['echo', '{message}'],
            ),
        ],
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
    )

    POD_CONFIG = ctr_models.PodConfig(
        name='dummy',
        version='0.0.1',
        apps=[
            ctr_models.PodConfig.App(
                name='foo',
                exec=['echo', 'hello world'],
            ),
        ],
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
            ctr_models.PodConfig.Mount(
                source='/path/to/ops/dir/volumes/some-volume',
                target='/some/where',
            ),
        ],
    )

    DEPLOY_INSTRUCTION = models.PodDeployInstruction(
        label='//foo/bar:dummy',
        pod_config_template=POD_CONFIG_TEMPLATE,
        volumes=[
            models.PodDeployInstruction.Volume(
                label='//foo/bar:some-volume',
                version='0.0.3',
                target='/some/where',
            ),
        ],
    )

    def test_make_pod_config(self):
        self.assertEqual(
            pod_ops_dirs.PodOpsDir._make_pod_config(
                self.DEPLOY_INSTRUCTION,
                Path('/path/to/ops/dir'),
                {'message': 'hello world'},
            ),
            self.POD_CONFIG,
        )


if __name__ == '__main__':
    unittest.main()
