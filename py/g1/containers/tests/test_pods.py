import unittest
import unittest.mock

import datetime
import io
import uuid

from g1.bases import datetimes
from g1.containers import bases
from g1.containers import builders
from g1.containers import images
from g1.containers import pods

from tests import fixtures


class PodsTest(fixtures.TestCaseBase):

    sample_pod_id = '01234567-89ab-cdef-0123-456789abcdef'

    sample_config = pods.PodConfig(
        name='test-pod',
        version='0.0.1',
        apps=[
            pods.PodConfig.App(
                name='hello',
                exec=['/bin/echo', 'hello', 'world'],
            ),
        ],
        images=[
            pods.PodConfig.Image(
                name='base',
                version='0.0.1',
            ),
            pods.PodConfig.Image(
                name='sample-app',
                version='1.0',
            ),
        ],
        volumes=[
            pods.PodConfig.Volume(
                source='/dev/null',
                target='/this/is/pod/path',
                read_only=True,
            ),
        ],
    )

    sample_image_id = '0123456789abcdef' * 4

    sample_metadata = images.ImageMetadata(
        name='sample-app',
        version='1.0',
    )

    def setUp(self):
        super().setUp()
        bases.cmd_init()
        images.cmd_init()
        pods.cmd_init()
        self.sample_pod_dir_path = pods.get_pod_dir_path(self.sample_pod_id)

    @staticmethod
    def make_pod_id(id_int):
        return str(uuid.UUID(int=id_int))

    @staticmethod
    def create_pod_dir(pod_id, config):
        pod_dir_path = pods.get_pod_dir_path(pod_id)
        pod_dir_path.mkdir()
        pods.setup_pod_dir_barely(pod_dir_path, config)

    @staticmethod
    def list_pod_dir_paths():
        return sorted(p.name for p in pods.iter_pod_dir_paths())

    @staticmethod
    def list_active():
        return sorted(p.name for p in pods.get_active_path().iterdir())

    @staticmethod
    def list_graveyard():
        return sorted(p.name for p in pods.get_graveyard_path().iterdir())

    @staticmethod
    def list_tmp():
        return sorted(p.name for p in pods.get_tmp_path().iterdir())

    @staticmethod
    def make_image_id(id_int):
        return '%064d' % id_int

    @staticmethod
    def create_image_dir(image_id, metadata):
        image_dir_path = images.get_image_dir_path(image_id)
        image_dir_path.mkdir()
        bases.write_jsonobject(
            metadata,
            images.get_metadata_path(image_dir_path),
        )
        images.get_rootfs_path(image_dir_path).mkdir()

    #
    # Top-level commands.
    #

    def test_cmd_init(self):
        self.assertEqual(
            sorted(p.name for p in pods.get_pod_repo_path().iterdir()),
            ['active', 'graveyard', 'tmp'],
        )

    def test_cmd_list(self):

        def cmd_list():
            return sorted(result['id'] for result in pods.cmd_list())

        self.assertEqual(cmd_list(), [])

        self.create_pod_dir(self.sample_pod_id, self.sample_config)
        for i, image in enumerate(self.sample_config.images):
            self.create_image_dir(
                self.make_image_id(i + 1),
                images.ImageMetadata(name=image.name, version=image.version),
            )
        self.assertEqual(cmd_list(), [self.sample_pod_id])

    def test_cmd_show(self):
        with self.assertRaisesRegex(AssertionError, r'expect.*is_dir'):
            pods.cmd_show(self.sample_pod_id)

        self.create_pod_dir(self.sample_pod_id, self.sample_config)
        self.assertEqual(
            pods.cmd_show(self.sample_pod_id),
            [{
                'name': 'hello',
                'status': None,
                'last-updated': None,
            }],
        )

    def test_cmd_cat_config(self):
        with self.assertRaisesRegex(AssertionError, r'expect.*is_file'):
            pods.cmd_cat_config(self.sample_pod_id, io.BytesIO())

        self.create_pod_dir(self.sample_pod_id, self.sample_config)
        buffer = io.BytesIO()
        pods.cmd_cat_config(self.sample_pod_id, buffer)
        self.assertEqual(
            buffer.getvalue(),
            pods.get_config_path(self.sample_pod_dir_path).read_bytes(),
        )

    def test_cmd_prepare(self):
        config_path = self.test_repo_path / 'sample-config'
        bases.write_jsonobject(self.sample_config, config_path)
        for i, image in enumerate(self.sample_config.images):
            self.create_image_dir(
                self.make_image_id(i + 1),
                images.ImageMetadata(name=image.name, version=image.version),
            )
        self.assertEqual(self.list_pod_dir_paths(), [])
        self.assertEqual(list(pods.get_tmp_path().iterdir()), [])

        with unittest.mock.patch.multiple(
            pods.__name__,
            subprocess=unittest.mock.DEFAULT,
            # We don't have a valid base image, and so we can't really
            # call ``builders.generate_unit_file``, etc.
            builders=unittest.mock.DEFAULT,
            generate_hostname=unittest.mock.DEFAULT,
        ):
            pods.cmd_prepare(self.sample_pod_id, config_path)
        self.assertEqual(self.list_pod_dir_paths(), [self.sample_pod_id])
        self.assertEqual(list(pods.get_tmp_path().iterdir()), [])

        self.assertFalse(self.check_exclusive(self.sample_pod_dir_path))

    def test_cmd_remove(self):
        config_path = self.test_repo_path / 'sample-config'
        bases.write_jsonobject(self.sample_config, config_path)
        self.assertEqual(self.list_pod_dir_paths(), [])
        self.assertEqual(list(pods.get_graveyard_path().iterdir()), [])
        self.assertEqual(list(pods.get_tmp_path().iterdir()), [])

        self.create_pod_dir(self.sample_pod_id, self.sample_config)
        self.assertEqual(self.list_pod_dir_paths(), [self.sample_pod_id])
        self.assertEqual(list(pods.get_graveyard_path().iterdir()), [])
        self.assertEqual(list(pods.get_tmp_path().iterdir()), [])

        with unittest.mock.patch(pods.__name__ + '.subprocess'):
            pods.cmd_remove(self.sample_pod_id)
        self.assertEqual(self.list_pod_dir_paths(), [])
        self.assertEqual(list(pods.get_graveyard_path().iterdir()), [])
        self.assertEqual(list(pods.get_tmp_path().iterdir()), [])

    def test_cmd_cleanup(self):
        future = datetimes.utcnow() + datetime.timedelta(days=1)
        pod_id_1 = self.make_pod_id(1)
        pod_id_2 = self.make_pod_id(2)
        self.create_pod_dir(pod_id_1, self.sample_config)
        self.create_pod_dir(pod_id_2, self.sample_config)
        self.assertEqual(self.list_active(), [pod_id_1, pod_id_2])
        self.assertEqual(self.list_graveyard(), [])
        self.assertEqual(self.list_tmp(), [])

        with self.using_exclusive(pods.get_pod_dir_path(pod_id_1)):
            pods.cmd_cleanup(datetimes.utcnow() + datetime.timedelta(days=1))
        self.assertEqual(self.list_active(), [pod_id_1])
        self.assertEqual(self.list_graveyard(), [])
        self.assertEqual(self.list_tmp(), [])

        pods.cmd_cleanup(future)
        self.assertEqual(self.list_active(), [])
        self.assertEqual(self.list_graveyard(), [])
        self.assertEqual(self.list_tmp(), [])

    def test_cleanup_active(self):
        future = datetimes.utcnow() + datetime.timedelta(days=1)
        pod_id_1 = self.make_pod_id(1)
        pod_id_2 = self.make_pod_id(2)
        self.create_pod_dir(pod_id_1, self.sample_config)
        self.create_pod_dir(pod_id_2, self.sample_config)
        self.assertEqual(self.list_active(), [pod_id_1, pod_id_2])
        self.assertEqual(self.list_graveyard(), [])
        self.assertEqual(self.list_tmp(), [])

        with self.using_exclusive(pods.get_pod_dir_path(pod_id_1)):
            pods.cleanup_active(future)
        self.assertEqual(self.list_active(), [pod_id_1])
        self.assertEqual(self.list_graveyard(), [pod_id_2])
        self.assertEqual(self.list_tmp(), [])

        pods.cleanup_active(future)
        self.assertEqual(self.list_active(), [])
        self.assertEqual(self.list_graveyard(), [pod_id_1, pod_id_2])
        self.assertEqual(self.list_tmp(), [])

    #
    # Locking strategy.
    #

    def test_create_tmp_pod_dir(self):
        tmp_path = pods.create_tmp_pod_dir()
        self.assertFalse(self.check_exclusive(tmp_path))

    def test_is_pod_dir_locked(self):
        self.assertFalse(pods.is_pod_dir_locked(self.test_repo_path))
        with self.using_shared(self.test_repo_path):
            self.assertTrue(pods.is_pod_dir_locked(self.test_repo_path))

    #
    # Data type.
    #

    def test_config(self):
        with self.assertRaisesRegex(AssertionError, r'expect non-empty'):
            pods.PodConfig(
                name='test-pod',
                version='0.0.1',
                apps=self.sample_config.apps,
                images=[],
            )
        with self.assertRaisesRegex(
            AssertionError, r'expect unique app names:'
        ):
            pods.PodConfig(
                name='test-pod',
                version='0.0.1',
                apps=[
                    pods.PodConfig.App(name='some-app', exec=['/bin/true']),
                    pods.PodConfig.App(name='some-app', exec=['/bin/false']),
                ],
                images=self.sample_config.images,
            )
        with self.assertRaisesRegex(
            AssertionError, r'expect unique volume targets:'
        ):
            pods.PodConfig(
                name='test-pod',
                version='0.0.1',
                apps=self.sample_config.apps,
                images=self.sample_config.images,
                volumes=[
                    pods.PodConfig.Volume(source='/p', target='/a'),
                    pods.PodConfig.Volume(source='/q', target='/a'),
                ],
            )
        with self.assertRaisesRegex(AssertionError, r'expect only one'):
            pods.PodConfig.Image()
        with self.assertRaisesRegex(AssertionError, r'expect.*xor.*be false'):
            pods.PodConfig.Image(name='name')
        with self.assertRaisesRegex(AssertionError, r'expect.*is_absolute'):
            pods.PodConfig.Volume(source='foo', target='/bar')
        with self.assertRaisesRegex(AssertionError, r'expect.*is_absolute'):
            pods.PodConfig.Volume(source='/foo', target='bar')

    def test_validate_id(self):
        self.assertEqual(
            pods.validate_id(self.sample_pod_id), self.sample_pod_id
        )
        for test_data in (
            '',
            '01234567-89AB-CDEF-0123-456789ABCDEF',
            '01234567-89ab-cdef-0123-456789abcde',
        ):
            with self.subTest(test_data):
                with self.assertRaisesRegex(
                    AssertionError, r'expect .*fullmatch*.'
                ):
                    pods.validate_id(test_data)

    def test_generate_id(self):
        id1 = pods.generate_id()
        id2 = pods.generate_id()
        self.assertNotEqual(id1, id2)
        self.assertEqual(pods.validate_id(id1), id1)
        self.assertEqual(pods.validate_id(id2), id2)

    #
    # Repo layout.
    #

    def test_repo_layout(self):
        for path1, path2 in (
            (
                pods.get_pod_repo_path(),
                bases.get_repo_path() / 'pods',
            ),
            (
                pods.get_active_path(),
                pods.get_pod_repo_path() / 'active',
            ),
            (
                pods.get_graveyard_path(),
                pods.get_pod_repo_path() / 'graveyard',
            ),
            (
                pods.get_tmp_path(),
                pods.get_pod_repo_path() / 'tmp',
            ),
            (
                pods.get_pod_dir_path(self.sample_pod_id),
                pods.get_active_path() / self.sample_pod_id,
            ),
            (
                pods.get_id(self.sample_pod_dir_path),
                self.sample_pod_id,
            ),
            (
                pods.get_config_path(self.sample_pod_dir_path),
                pods.get_active_path() / self.sample_pod_id / 'config',
            ),
            (
                pods.get_deps_path(self.sample_pod_dir_path),
                pods.get_active_path() / self.sample_pod_id / 'deps',
            ),
            (
                pods.get_work_path(self.sample_pod_dir_path),
                pods.get_active_path() / self.sample_pod_id / 'work',
            ),
            (
                pods.get_upper_path(self.sample_pod_dir_path),
                pods.get_active_path() / self.sample_pod_id / 'upper',
            ),
            (
                pods.get_rootfs_path(self.sample_pod_dir_path),
                pods.get_active_path() / self.sample_pod_id / 'rootfs',
            ),
        ):
            with self.subTest((path1, path2)):
                self.assertEqual(path1, path2)

    #
    # Top-level directories.
    #

    def test_cleanup_top_dir(self):
        pod_id_1 = self.make_pod_id(1)
        pod_id_2 = self.make_pod_id(2)
        self.create_pod_dir(pod_id_1, self.sample_config)
        self.create_pod_dir(pod_id_2, self.sample_config)
        self.assertEqual(self.list_pod_dir_paths(), [pod_id_1, pod_id_2])

        with unittest.mock.patch(pods.__name__ + '.subprocess'):

            with bases.acquiring_exclusive(pods.get_pod_dir_path(pod_id_2)):
                pods.cleanup_top_dir(pods.get_active_path())
            self.assertEqual(self.list_pod_dir_paths(), [pod_id_2])

            pods.cleanup_top_dir(pods.get_active_path())
            self.assertEqual(self.list_pod_dir_paths(), [])

    #
    # Pod directories.
    #

    def test_iter_pod_dir_paths(self):
        pod_id_1 = self.make_pod_id(1)
        pod_id_2 = self.make_pod_id(2)

        (pods.get_active_path() / 'irrelevant').touch()
        self.assertEqual(self.list_pod_dir_paths(), [])
        self.assertEqual(self.list_active(), ['irrelevant'])

        self.create_pod_dir(pod_id_2, self.sample_config)
        self.assertEqual(self.list_pod_dir_paths(), [pod_id_2])

        (pods.get_active_path() / pod_id_1).mkdir()
        self.assertEqual(self.list_pod_dir_paths(), [pod_id_1, pod_id_2])

    def test_maybe_move_pod_dir_to_active(self):
        self.assertEqual(self.list_pod_dir_paths(), [])

        path = self.test_repo_path / 'some-dir'
        path.mkdir()
        self.assertTrue(path.exists())
        self.assertTrue(
            pods.maybe_move_pod_dir_to_active(path, self.sample_pod_id)
        )
        self.assertEqual(self.list_pod_dir_paths(), [self.sample_pod_id])
        self.assertFalse(path.exists())

        path.mkdir()
        self.assertFalse(
            pods.maybe_move_pod_dir_to_active(path, self.sample_pod_id)
        )

    def test_move_pod_dir_to_graveyard(self):

        def list_grave_paths():
            return sorted(p.name for p in pods.get_graveyard_path().iterdir())

        self.assertEqual(list_grave_paths(), [])

        self.create_pod_dir(self.sample_pod_id, self.sample_config)
        self.assertTrue(self.sample_pod_dir_path.exists())
        pods.move_pod_dir_to_graveyard(self.sample_pod_dir_path)
        self.assertEqual(list_grave_paths(), [self.sample_pod_id])
        self.assertFalse(self.sample_pod_dir_path.exists())

    #
    # Pod directory.
    #

    def test_prepare_pod_dir(self):
        self.sample_pod_dir_path.mkdir()
        for i, image in enumerate(self.sample_config.images):
            self.create_image_dir(
                self.make_image_id(i + 1),
                images.ImageMetadata(name=image.name, version=image.version),
            )
        with unittest.mock.patch.multiple(
            pods.__name__,
            subprocess=unittest.mock.DEFAULT,
            # We don't have a valid base image, and so we can't really
            # call ``builders.generate_unit_file``, etc.
            builders=unittest.mock.DEFAULT,
            generate_hostname=unittest.mock.DEFAULT,
        ):
            pods.prepare_pod_dir(
                self.sample_pod_dir_path,
                self.sample_pod_id,
                self.sample_config,
            )

    def test_setup_pod_dir_barely(self):
        self.create_pod_dir(self.sample_pod_id, self.sample_config)
        self.assertTrue(
            pods.get_config_path(self.sample_pod_dir_path).is_file()
        )
        self.assertTrue(pods.get_deps_path(self.sample_pod_dir_path).is_dir())
        self.assertTrue(pods.get_work_path(self.sample_pod_dir_path).is_dir())
        self.assertTrue(pods.get_upper_path(self.sample_pod_dir_path).is_dir())
        self.assertTrue(
            pods.get_rootfs_path(self.sample_pod_dir_path).is_dir()
        )
        self.assertEqual(
            sorted(p.name for p in self.sample_pod_dir_path.iterdir()),
            ['config', 'deps', 'rootfs', 'upper', 'work'],
        )

    def test_remove_pod_dir(self):
        self.create_pod_dir(self.sample_pod_id, self.sample_config)
        self.assertTrue(self.sample_pod_dir_path.is_dir())
        with unittest.mock.patch(pods.__name__ + '.subprocess'):
            pods.remove_pod_dir(self.sample_pod_dir_path)
        self.assertFalse(self.sample_pod_dir_path.exists())

    #
    # Pod.
    #

    @unittest.mock.patch(pods.__name__ + '.subprocess')
    def test_mount_overlay(self, subprocess_mock):
        image_id_1 = self.make_image_id(1)
        image_id_2 = self.make_image_id(2)
        self.create_image_dir(
            image_id_1,
            images.ImageMetadata(name='base', version='0.0.1'),
        )
        self.create_image_dir(image_id_2, self.sample_metadata)

        pods.mount_overlay(self.sample_pod_dir_path, self.sample_config)
        subprocess_mock.run.assert_called_once_with(
            [
                'mount',
                '-t',
                'overlay',
                '-o',
                'lowerdir=%s,upperdir=%s,workdir=%s' % (
                    ':'.join([
                        str(pods.get_image_rootfs_path(image_id_2)),
                        str(pods.get_image_rootfs_path(image_id_1)),
                    ]),
                    pods.get_upper_path(self.sample_pod_dir_path),
                    pods.get_work_path(self.sample_pod_dir_path),
                ),
                'overlay',
                str(pods.get_rootfs_path(self.sample_pod_dir_path)),
            ],
            check=True,
        )

    def test_make_bind_argument(self):
        self.assertEqual(
            pods.make_bind_argument(
                pods.PodConfig.Volume(
                    source='/a',
                    target='/b',
                    read_only=True,
                )
            ),
            '--bind-ro=/a:/b',
        )
        self.assertEqual(
            pods.make_bind_argument(
                pods.PodConfig.Volume(
                    source='/a',
                    target='/b',
                    read_only=False,
                )
            ),
            '--bind=/a:/b',
        )

    #
    # Configs.
    #

    def test_iter_configs(self):

        def list_configs():
            return sorted((p.name, c) for p, c in pods.iter_configs())

        pod_id_1 = self.make_pod_id(1)
        pod_id_2 = self.make_pod_id(2)

        self.assertEqual(list_configs(), [])

        self.create_pod_dir(pod_id_2, self.sample_config)
        self.assertEqual(list_configs(), [(pod_id_2, self.sample_config)])

        self.create_pod_dir(pod_id_1, self.sample_config)
        self.assertEqual(
            list_configs(),
            [(pod_id_1, self.sample_config), (pod_id_2, self.sample_config)],
        )

    def test_read_config(self):
        self.create_pod_dir(self.sample_pod_id, self.sample_config)
        self.assertEqual(
            pods.read_config(self.sample_pod_dir_path),
            self.sample_config,
        )

    def test_write_config(self):
        self.assertFalse((self.test_repo_path / 'config').exists())
        pods.write_config(self.sample_config, self.test_repo_path)
        self.assertTrue((self.test_repo_path / 'config').exists())
        self.assertEqual(
            pods.read_config(self.test_repo_path),
            self.sample_config,
        )

    def test_iter_image_ids(self):

        def list_image_ids(config):
            return sorted(pods.iter_image_ids(config))

        self.create_image_dir(self.sample_image_id, self.sample_metadata)
        images.cmd_tag(image_id=self.sample_image_id, new_tag='some-tag')

        config = pods.PodConfig(
            name='test-pod',
            version='0.0.1',
            apps=self.sample_config.apps,
            images=[pods.PodConfig.Image(id=self.sample_image_id)],
        )
        self.assertEqual(list_image_ids(config), [self.sample_image_id])

        config = pods.PodConfig(
            name='test-pod',
            version='0.0.1',
            apps=self.sample_config.apps,
            images=[pods.PodConfig.Image(name='sample-app', version='1.0')],
        )
        self.assertEqual(list_image_ids(config), [self.sample_image_id])

        config = pods.PodConfig(
            name='test-pod',
            version='0.0.1',
            apps=self.sample_config.apps,
            images=[pods.PodConfig.Image(tag='some-tag')],
        )
        self.assertEqual(list_image_ids(config), [self.sample_image_id])

        config = pods.PodConfig(
            name='test-pod',
            version='0.0.1',
            apps=self.sample_config.apps,
            images=[pods.PodConfig.Image(name='no-such-app', version='1.0')],
        )
        with self.assertRaisesRegex(AssertionError, r'expect non-None value'):
            list_image_ids(config)

        config = pods.PodConfig(
            name='test-pod',
            version='0.0.1',
            apps=self.sample_config.apps,
            images=[pods.PodConfig.Image(tag='no-such-tag')],
        )
        with self.assertRaisesRegex(AssertionError, r'expect non-None value'):
            list_image_ids(config)

    #
    # Dependent images.
    #

    def test_add_ref_image_ids(self):

        def list_image_ids():
            return sorted(
                p.name
                for p in pods.get_deps_path(self.sample_pod_dir_path).iterdir()
            )

        image_id_1 = self.make_image_id(1)
        image_id_2 = self.make_image_id(2)
        self.create_pod_dir(self.sample_pod_id, self.sample_config)
        self.create_image_dir(image_id_1, self.sample_metadata)
        self.create_image_dir(image_id_2, self.sample_metadata)
        self.assertEqual(list_image_ids(), [])
        self.assertEqual(
            images._get_ref_count(images.get_image_dir_path(image_id_1)), 1
        )
        self.assertEqual(
            images._get_ref_count(images.get_image_dir_path(image_id_2)), 1
        )

        pods.add_ref_image_ids(
            self.sample_pod_dir_path,
            pods.PodConfig(
                name='test-pod',
                version='0.0.1',
                apps=self.sample_config.apps,
                images=[
                    pods.PodConfig.Image(id=image_id_1),
                    pods.PodConfig.Image(id=image_id_2),
                ],
            ),
        )
        self.assertEqual(list_image_ids(), [image_id_1, image_id_2])
        self.assertEqual(
            images._get_ref_count(images.get_image_dir_path(image_id_1)), 2
        )
        self.assertEqual(
            images._get_ref_count(images.get_image_dir_path(image_id_2)), 2
        )

    def test_iter_ref_image_ids(self):

        def list_ref_image_ids(pod_dir_path):
            return sorted(pods.iter_ref_image_ids(pod_dir_path))

        image_id_1 = self.make_image_id(1)
        image_id_2 = self.make_image_id(2)
        self.create_pod_dir(self.sample_pod_id, self.sample_config)
        self.create_image_dir(image_id_1, self.sample_metadata)
        self.create_image_dir(image_id_2, self.sample_metadata)
        self.assertEqual(list_ref_image_ids(self.sample_pod_dir_path), [])

        pods.add_ref_image_ids(
            self.sample_pod_dir_path,
            pods.PodConfig(
                name='test-pod',
                version='0.0.1',
                apps=self.sample_config.apps,
                images=[
                    pods.PodConfig.Image(id=image_id_1),
                    pods.PodConfig.Image(id=image_id_2),
                ],
            ),
        )
        self.assertEqual(
            list_ref_image_ids(self.sample_pod_dir_path),
            [image_id_1, image_id_2],
        )

    #
    # Pod runtime state.
    #

    def test_get_pod_status(self):
        self.assertEqual(
            pods.get_pod_status(self.sample_pod_dir_path, self.sample_config),
            {},
        )

        self.create_pod_dir(self.sample_pod_id, self.sample_config)
        app = self.sample_config.apps[0]
        path = builders._get_pod_app_exit_status_path(
            pods.get_rootfs_path(self.sample_pod_dir_path), app
        )
        path.parent.mkdir(parents=True)
        path.write_text('99')
        pod_status = pods.get_pod_status(
            self.sample_pod_dir_path, self.sample_config
        )
        self.assertEqual(list(pod_status.keys()), [app.name])
        self.assertEqual(pod_status[app.name][0], 99)

    def test_get_last_updated(self):
        self.assertIsNone(pods.get_last_updated({}))
        self.assertEqual(
            pods.get_last_updated({
                'app-1': (0, datetime.datetime(2001, 1, 1)),
            }),
            datetime.datetime(2001, 1, 1),
        )
        self.assertEqual(
            pods.get_last_updated({
                'app-1': (0, datetime.datetime(2001, 1, 1)),
                'app-2': (0, datetime.datetime(2002, 1, 1)),
            }),
            datetime.datetime(2002, 1, 1),
        )

    #
    # Helpers for mount/umount.
    #

    def test_umount(self):
        path1 = pods.get_pod_repo_path() / 'some-file'
        path2 = pods.get_pod_repo_path() / 'some-dir'
        path3 = pods.get_pod_repo_path() / 'link-to-dir'
        path1.touch()
        path2.mkdir()
        path3.symlink_to(path2)
        pods.umount(path1)
        pods.umount(path2)
        with self.assertRaisesRegex(AssertionError, r'expect not.*is_symlink'):
            pods.umount(path3)


if __name__ == '__main__':
    unittest.main()
