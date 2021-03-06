import unittest
import unittest.mock

import datetime
import io
import uuid

from g1.bases import datetimes
from g1.containers import bases
from g1.containers import builders
from g1.containers import images
from g1.containers import models
from g1.containers import pods
from g1.files import locks
from g1.texts import jsons

try:
    from g1.devtools.tests import filelocks
except ImportError:
    filelocks = None

from tests import fixtures


class PodsTest(
    fixtures.TestCaseBase,
    filelocks.Fixture if filelocks else object,
):

    sample_pod_id = '01234567-89ab-cdef-0123-456789abcdef'

    sample_config = models.PodConfig(
        name='test-pod',
        version='0.0.1',
        apps=[
            models.PodConfig.App(
                name='hello',
                exec=['/bin/echo', 'hello', 'world'],
            ),
        ],
        images=[
            models.PodConfig.Image(
                name='base',
                version='0.0.1',
            ),
            models.PodConfig.Image(
                name='sample-app',
                version='1.0',
            ),
        ],
        mounts=[
            models.PodConfig.Mount(
                source='/dev/null',
                target='/this/is/pod/path',
                read_only=True,
            ),
        ],
        overlays=[
            models.PodConfig.Overlay(
                sources=[''],
                target='/this/is/some/other/pod/path',
                read_only=False,
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
        self.sample_pod_dir_path = pods._get_pod_dir_path(self.sample_pod_id)
        patcher = unittest.mock.patch.object(pods, 'journals')
        self.mock_journals = patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def make_pod_id(id_int):
        return str(uuid.UUID(int=id_int))

    @staticmethod
    def create_pod_dir(pod_id, config):
        pod_dir_path = pods._get_pod_dir_path(pod_id)
        pod_dir_path.mkdir()
        pods._setup_pod_dir_barely(pod_dir_path, config)
        pods._pod_dir_create_config(pod_dir_path, config)

    @staticmethod
    def list_pod_dir_paths():
        return sorted(p.name for p in pods._iter_pod_dir_paths())

    @staticmethod
    def list_active():
        return sorted(p.name for p in pods._get_active_path().iterdir())

    @staticmethod
    def list_graveyard():
        return sorted(p.name for p in pods._get_graveyard_path().iterdir())

    @staticmethod
    def list_tmp():
        return sorted(p.name for p in pods._get_tmp_path().iterdir())

    @staticmethod
    def make_image_id(id_int):
        return '%064d' % id_int

    @staticmethod
    def create_image_dir(image_id, metadata):
        image_dir_path = images.get_image_dir_path(image_id)
        image_dir_path.mkdir()
        jsons.dump_dataobject(
            metadata,
            images._get_metadata_path(image_dir_path),
        )
        images.get_rootfs_path(image_dir_path).mkdir()

    #
    # Top-level commands.
    #

    def test_cmd_init(self):
        self.assertEqual(
            sorted(p.name for p in pods._get_pod_repo_path().iterdir()),
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
                'ref-count': 1,
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
            pods._get_config_path(self.sample_pod_dir_path).read_bytes(),
        )

    @unittest.skipUnless(filelocks, 'g1.tests.filelocks unavailable')
    def test_cmd_prepare(self):
        config_path = self.test_repo_path / 'sample-config'
        jsons.dump_dataobject(self.sample_config, config_path)
        for i, image in enumerate(self.sample_config.images):
            self.create_image_dir(
                self.make_image_id(i + 1),
                images.ImageMetadata(name=image.name, version=image.version),
            )
        self.assertEqual(self.list_pod_dir_paths(), [])
        self.assertEqual(list(pods._get_tmp_path().iterdir()), [])

        with unittest.mock.patch.multiple(
            pods.__name__,
            scripts=unittest.mock.DEFAULT,
            # We don't have a valid base image, and so we can't really
            # call ``builders.generate_unit_file``, etc.
            builders=unittest.mock.DEFAULT,
            _generate_hostname=unittest.mock.DEFAULT,
        ):
            pods.cmd_prepare(self.sample_pod_id, config_path)
        self.assertEqual(self.list_pod_dir_paths(), [self.sample_pod_id])
        self.assertEqual(list(pods._get_tmp_path().iterdir()), [])

        self.assertFalse(self.check_exclusive(self.sample_pod_dir_path))

    def test_cmd_remove(self):
        config_path = self.test_repo_path / 'sample-config'
        jsons.dump_dataobject(self.sample_config, config_path)
        self.assertEqual(self.list_pod_dir_paths(), [])
        self.assertEqual(list(pods._get_graveyard_path().iterdir()), [])
        self.assertEqual(list(pods._get_tmp_path().iterdir()), [])

        self.create_pod_dir(self.sample_pod_id, self.sample_config)
        self.assertEqual(pods._get_ref_count(self.sample_pod_dir_path), 1)
        self.assertEqual(self.list_pod_dir_paths(), [self.sample_pod_id])
        self.assertEqual(list(pods._get_graveyard_path().iterdir()), [])
        self.assertEqual(list(pods._get_tmp_path().iterdir()), [])

        ref_path = self.test_repo_path / 'ref'
        pods.cmd_add_ref(self.sample_pod_id, ref_path)
        with unittest.mock.patch(pods.__name__ + '.scripts'):
            with self.assertRaisesRegex(
                AssertionError, r'expect x <= 1, not 2'
            ):
                pods.cmd_remove(self.sample_pod_id)
        self.assertEqual(pods._get_ref_count(self.sample_pod_dir_path), 2)
        self.assertEqual(self.list_pod_dir_paths(), [self.sample_pod_id])
        self.assertEqual(list(pods._get_graveyard_path().iterdir()), [])
        self.assertEqual(list(pods._get_tmp_path().iterdir()), [])
        self.mock_journals.remove_journal_dir.assert_not_called()

        ref_path.unlink()
        with unittest.mock.patch(pods.__name__ + '.scripts'):
            pods.cmd_remove(self.sample_pod_id)
        self.assertEqual(self.list_pod_dir_paths(), [])
        self.assertEqual(list(pods._get_graveyard_path().iterdir()), [])
        self.assertEqual(list(pods._get_tmp_path().iterdir()), [])
        self.mock_journals.remove_journal_dir.assert_called_once_with(
            self.sample_pod_id
        )

    @unittest.skipUnless(filelocks, 'g1.tests.filelocks unavailable')
    def test_cmd_cleanup(self):
        future = datetimes.utcnow() + datetime.timedelta(days=1)
        pod_id_1 = self.make_pod_id(1)
        pod_id_2 = self.make_pod_id(2)
        self.create_pod_dir(pod_id_1, self.sample_config)
        self.create_pod_dir(pod_id_2, self.sample_config)
        self.assertEqual(self.list_active(), [pod_id_1, pod_id_2])
        self.assertEqual(self.list_graveyard(), [])
        self.assertEqual(self.list_tmp(), [])

        ref_path = self.test_repo_path / 'ref'
        pods.cmd_add_ref(pod_id_1, ref_path)
        pods.cmd_cleanup(future)
        self.assertEqual(self.list_active(), [pod_id_1])
        self.assertEqual(self.list_graveyard(), [])
        self.assertEqual(self.list_tmp(), [])
        ref_path.unlink()
        self.mock_journals.remove_journal_dir.assert_called_once_with(pod_id_2)

        self.mock_journals.remove_journal_dir.reset_mock()
        with self.using_exclusive(pods._get_pod_dir_path(pod_id_1)):
            pods.cmd_cleanup(future)
        self.assertEqual(self.list_active(), [pod_id_1])
        self.assertEqual(self.list_graveyard(), [])
        self.assertEqual(self.list_tmp(), [])
        self.mock_journals.remove_journal_dir.assert_not_called()

        self.mock_journals.remove_journal_dir.reset_mock()
        pods.cmd_cleanup(future)
        self.assertEqual(self.list_active(), [])
        self.assertEqual(self.list_graveyard(), [])
        self.assertEqual(self.list_tmp(), [])
        self.mock_journals.remove_journal_dir.assert_called_once_with(pod_id_1)

    @unittest.skipUnless(filelocks, 'g1.tests.filelocks unavailable')
    def test_cleanup_active(self):
        future = datetimes.utcnow() + datetime.timedelta(days=1)
        pod_id_1 = self.make_pod_id(1)
        pod_id_2 = self.make_pod_id(2)
        self.create_pod_dir(pod_id_1, self.sample_config)
        self.create_pod_dir(pod_id_2, self.sample_config)
        self.assertEqual(self.list_active(), [pod_id_1, pod_id_2])
        self.assertEqual(self.list_graveyard(), [])
        self.assertEqual(self.list_tmp(), [])

        with self.using_exclusive(pods._get_pod_dir_path(pod_id_1)):
            pods._cleanup_active(future)
        self.assertEqual(self.list_active(), [pod_id_1])
        self.assertEqual(self.list_graveyard(), [pod_id_2])
        self.assertEqual(self.list_tmp(), [])
        self.mock_journals.remove_journal_dir.assert_called_once_with(pod_id_2)

        self.mock_journals.remove_journal_dir.reset_mock()
        pods._cleanup_active(future)
        self.assertEqual(self.list_active(), [])
        self.assertEqual(self.list_graveyard(), [pod_id_1, pod_id_2])
        self.assertEqual(self.list_tmp(), [])
        self.mock_journals.remove_journal_dir.assert_called_once_with(pod_id_1)

    #
    # Locking strategy.
    #

    @unittest.skipUnless(filelocks, 'g1.tests.filelocks unavailable')
    def test_create_tmp_pod_dir(self):
        tmp_path = pods._create_tmp_pod_dir()
        self.assertFalse(self.check_exclusive(tmp_path))

    #
    # Data type.
    #

    def test_config(self):
        with self.assertRaisesRegex(AssertionError, r'expect non-empty'):
            models.PodConfig(
                name='test-pod',
                version='0.0.1',
                apps=self.sample_config.apps,
                images=[],
            )
        with self.assertRaisesRegex(
            AssertionError, r'expect unique elements in '
        ):
            models.PodConfig(
                name='test-pod',
                version='0.0.1',
                apps=[
                    models.PodConfig.App(name='some-app', exec=['/bin/true']),
                    models.PodConfig.App(name='some-app', exec=['/bin/false']),
                ],
                images=self.sample_config.images,
            )
        with self.assertRaisesRegex(
            AssertionError, r'expect unique elements in '
        ):
            models.PodConfig(
                name='test-pod',
                version='0.0.1',
                apps=self.sample_config.apps,
                images=self.sample_config.images,
                mounts=[
                    models.PodConfig.Mount(source='/p', target='/a'),
                ],
                overlays=[
                    models.PodConfig.Overlay(sources=['/q'], target='/a'),
                ],
            )
        with self.assertRaisesRegex(AssertionError, r'expect only one'):
            models.PodConfig.Image()
        with self.assertRaisesRegex(AssertionError, r'expect.*xor.*be false'):
            models.PodConfig.Image(name='name')
        with self.assertRaisesRegex(AssertionError, r'expect.*is_absolute'):
            models.PodConfig.Mount(source='foo', target='/bar')
        with self.assertRaisesRegex(AssertionError, r'expect.*is_absolute'):
            models.PodConfig.Mount(source='/foo', target='bar')
        with self.assertRaisesRegex(AssertionError, r'expect non-empty'):
            models.PodConfig.Overlay(sources=[], target='/bar')
        with self.assertRaisesRegex(AssertionError, r'expect.*is_absolute'):
            models.PodConfig.Overlay(sources=['foo'], target='/bar')
        with self.assertRaisesRegex(AssertionError, r'expect.*is_absolute'):
            models.PodConfig.Overlay(sources=['/foo'], target='bar')
        with self.assertRaisesRegex(AssertionError, r'expect x == 1, not 0'):
            models.PodConfig.Overlay(sources=['', '/foo'], target='/bar')

    def test_validate_id(self):
        self.assertEqual(
            models.validate_pod_id(self.sample_pod_id), self.sample_pod_id
        )
        for test_data in (
            '',
            '01234567-89AB-CDEF-0123-456789ABCDEF',
            '01234567-89ab-cdef-0123-456789abcde',
        ):
            with self.subTest(test_data):
                with self.assertRaisesRegex(
                    AssertionError, r'expect .*fullmatch.*'
                ):
                    models.validate_pod_id(test_data)

    def test_id_converter(self):
        self.assertEqual(
            models.
            pod_id_to_machine_id('01234567-89ab-cdef-0123-456789abcdef'),
            '0123456789abcdef0123456789abcdef',
        )
        self.assertEqual(
            models.machine_id_to_pod_id('0123456789abcdef0123456789abcdef'),
            '01234567-89ab-cdef-0123-456789abcdef',
        )

    def test_generate_id(self):
        id1 = models.generate_pod_id()
        id2 = models.generate_pod_id()
        self.assertNotEqual(id1, id2)
        self.assertEqual(models.validate_pod_id(id1), id1)
        self.assertEqual(models.validate_pod_id(id2), id2)

    #
    # Repo layout.
    #

    def test_repo_layout(self):
        for path1, path2 in (
            (
                pods._get_pod_repo_path(),
                bases.get_repo_path() / 'pods',
            ),
            (
                pods._get_active_path(),
                pods._get_pod_repo_path() / 'active',
            ),
            (
                pods._get_graveyard_path(),
                pods._get_pod_repo_path() / 'graveyard',
            ),
            (
                pods._get_tmp_path(),
                pods._get_pod_repo_path() / 'tmp',
            ),
            (
                pods._get_pod_dir_path(self.sample_pod_id),
                pods._get_active_path() / self.sample_pod_id,
            ),
            (
                pods._get_id(self.sample_pod_dir_path),
                self.sample_pod_id,
            ),
            (
                pods._get_config_path(self.sample_pod_dir_path),
                pods._get_active_path() / self.sample_pod_id / 'config',
            ),
            (
                pods._get_orig_config_path(self.sample_pod_dir_path),
                pods._get_active_path() / self.sample_pod_id / 'config.orig',
            ),
            (
                pods._get_deps_path(self.sample_pod_dir_path),
                pods._get_active_path() / self.sample_pod_id / 'deps',
            ),
            (
                pods._get_work_path(self.sample_pod_dir_path),
                pods._get_active_path() / self.sample_pod_id / 'work',
            ),
            (
                pods._get_upper_path(self.sample_pod_dir_path),
                pods._get_active_path() / self.sample_pod_id / 'upper',
            ),
            (
                pods._get_rootfs_path(self.sample_pod_dir_path),
                pods._get_active_path() / self.sample_pod_id / 'rootfs',
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

        with unittest.mock.patch(pods.__name__ + '.scripts'):

            with locks.acquiring_exclusive(pods._get_pod_dir_path(pod_id_2)):
                pods._cleanup_top_dir(pods._get_active_path())
            self.assertEqual(self.list_pod_dir_paths(), [pod_id_2])

            pods._cleanup_top_dir(pods._get_active_path())
            self.assertEqual(self.list_pod_dir_paths(), [])

    #
    # Pod directories.
    #

    def test_iter_pod_dir_paths(self):
        pod_id_1 = self.make_pod_id(1)
        pod_id_2 = self.make_pod_id(2)

        (pods._get_active_path() / 'irrelevant').touch()
        self.assertEqual(self.list_pod_dir_paths(), [])
        self.assertEqual(self.list_active(), ['irrelevant'])

        self.create_pod_dir(pod_id_2, self.sample_config)
        self.assertEqual(self.list_pod_dir_paths(), [pod_id_2])

        (pods._get_active_path() / pod_id_1).mkdir()
        self.assertEqual(self.list_pod_dir_paths(), [pod_id_1, pod_id_2])

    def test_maybe_move_pod_dir_to_active(self):
        self.assertEqual(self.list_pod_dir_paths(), [])

        path = self.test_repo_path / 'some-dir'
        path.mkdir()
        self.assertTrue(path.exists())
        self.assertTrue(
            pods._maybe_move_pod_dir_to_active(path, self.sample_pod_id)
        )
        self.assertEqual(self.list_pod_dir_paths(), [self.sample_pod_id])
        self.assertFalse(path.exists())

        path.mkdir()
        self.assertFalse(
            pods._maybe_move_pod_dir_to_active(path, self.sample_pod_id)
        )

    def test_move_pod_dir_to_graveyard(self):

        def list_grave_paths():
            return sorted(p.name for p in pods._get_graveyard_path().iterdir())

        self.assertEqual(list_grave_paths(), [])

        self.create_pod_dir(self.sample_pod_id, self.sample_config)
        self.assertTrue(self.sample_pod_dir_path.exists())
        pods._move_pod_dir_to_graveyard(self.sample_pod_dir_path)
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
            scripts=unittest.mock.DEFAULT,
            # We don't have a valid base image, and so we can't really
            # call ``builders.generate_unit_file``, etc.
            builders=unittest.mock.DEFAULT,
            _generate_hostname=unittest.mock.DEFAULT,
        ):
            pods._prepare_pod_dir(
                self.sample_pod_dir_path,
                self.sample_pod_id,
                self.sample_config,
            )

    def test_setup_pod_dir_barely(self):
        pod_dir_path = pods._get_pod_dir_path(self.sample_pod_id)
        pod_dir_path.mkdir()
        pods._setup_pod_dir_barely(pod_dir_path, self.sample_config)
        self.assertFalse(
            pods._get_config_path(self.sample_pod_dir_path).is_file()
        )
        self.assertTrue(
            pods._get_orig_config_path(self.sample_pod_dir_path).is_file()
        )
        self.assertTrue(pods._get_deps_path(self.sample_pod_dir_path).is_dir())
        self.assertTrue(pods._get_work_path(self.sample_pod_dir_path).is_dir())
        self.assertTrue(
            pods._get_upper_path(self.sample_pod_dir_path).is_dir()
        )
        self.assertTrue(
            pods._get_rootfs_path(self.sample_pod_dir_path).is_dir()
        )
        self.assertEqual(
            sorted(p.name for p in self.sample_pod_dir_path.iterdir()),
            ['config.orig', 'deps', 'rootfs', 'upper', 'work'],
        )

    def test_remove_pod_dir(self):
        self.create_pod_dir(self.sample_pod_id, self.sample_config)
        self.assertTrue(self.sample_pod_dir_path.is_dir())
        with unittest.mock.patch(pods.__name__ + '.scripts'):
            pods._remove_pod_dir(self.sample_pod_dir_path)
        self.assertFalse(self.sample_pod_dir_path.exists())

    #
    # Pod.
    #

    @unittest.mock.patch(pods.__name__ + '.scripts')
    def test_mount_overlay(self, scripts_mock):
        image_id_1 = self.make_image_id(1)
        image_id_2 = self.make_image_id(2)
        self.create_image_dir(
            image_id_1,
            images.ImageMetadata(name='base', version='0.0.1'),
        )
        self.create_image_dir(image_id_2, self.sample_metadata)

        pods._mount_overlay(self.sample_pod_dir_path, self.sample_config)
        scripts_mock.run.assert_called_once_with([
            'mount',
            *('-t', 'overlay'),
            *(
                '-o',
                'lowerdir=%s,upperdir=%s,workdir=%s' % (
                    ':'.join([
                        str(pods._get_image_rootfs_path(image_id_2)),
                        str(pods._get_image_rootfs_path(image_id_1)),
                    ]),
                    pods._get_upper_path(self.sample_pod_dir_path),
                    pods._get_work_path(self.sample_pod_dir_path),
                ),
            ),
            'overlay',
            pods._get_rootfs_path(self.sample_pod_dir_path),
        ])

    def test_make_bind_argument(self):
        self.assertEqual(
            pods._make_bind_argument(
                models.PodConfig.Mount(
                    source='/a',
                    target='/b',
                    read_only=True,
                )
            ),
            '--bind-ro=/a:/b',
        )
        self.assertEqual(
            pods._make_bind_argument(
                models.PodConfig.Mount(
                    source='/a',
                    target='/b',
                    read_only=False,
                )
            ),
            '--bind=/a:/b',
        )

    def test_make_overlay_argument(self):
        self.assertEqual(
            pods._make_overlay_argument(
                models.PodConfig.Overlay(
                    sources=['/a', '/b'],
                    target='/c',
                    read_only=True,
                )
            ),
            '--overlay-ro=/a:/b:/c',
        )
        self.assertEqual(
            pods._make_overlay_argument(
                models.PodConfig.Overlay(
                    sources=['/a', ''],
                    target='/b',
                    read_only=False,
                )
            ),
            '--overlay=/a::/b',
        )

    #
    # Configs.
    #

    def test_iter_configs(self):

        def list_configs():
            return sorted((p.name, c) for p, c in pods._iter_configs())

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
            pods._read_config(self.sample_pod_dir_path),
            self.sample_config,
        )

    def test_write_config(self):
        self.assertFalse((self.test_repo_path / 'config').exists())
        pods._write_config(self.sample_config, self.test_repo_path)
        self.assertTrue((self.test_repo_path / 'config').exists())
        self.assertEqual(
            pods._read_config(self.test_repo_path),
            self.sample_config,
        )
        self.assertFalse((self.test_repo_path / 'config.orig').exists())

    def test_write_orig_config(self):
        self.assertFalse((self.test_repo_path / 'config.orig').exists())
        pods._write_orig_config(self.sample_config, self.test_repo_path)
        self.assertTrue((self.test_repo_path / 'config.orig').exists())
        self.assertEqual(
            pods._read_orig_config(self.test_repo_path),
            self.sample_config,
        )
        self.assertFalse((self.test_repo_path / 'config').exists())

    def test_iter_image_ids(self):

        def list_image_ids(config):
            return sorted(pods._iter_image_ids(config))

        self.create_image_dir(self.sample_image_id, self.sample_metadata)
        images.cmd_tag(image_id=self.sample_image_id, new_tag='some-tag')

        config = models.PodConfig(
            name='test-pod',
            version='0.0.1',
            apps=self.sample_config.apps,
            images=[models.PodConfig.Image(id=self.sample_image_id)],
        )
        self.assertEqual(list_image_ids(config), [self.sample_image_id])

        config = models.PodConfig(
            name='test-pod',
            version='0.0.1',
            apps=self.sample_config.apps,
            images=[models.PodConfig.Image(name='sample-app', version='1.0')],
        )
        self.assertEqual(list_image_ids(config), [self.sample_image_id])

        config = models.PodConfig(
            name='test-pod',
            version='0.0.1',
            apps=self.sample_config.apps,
            images=[models.PodConfig.Image(tag='some-tag')],
        )
        self.assertEqual(list_image_ids(config), [self.sample_image_id])

        config = models.PodConfig(
            name='test-pod',
            version='0.0.1',
            apps=self.sample_config.apps,
            images=[models.PodConfig.Image(name='no-such-app', version='1.0')],
        )
        with self.assertRaisesRegex(AssertionError, r'expect non-None value'):
            list_image_ids(config)

        config = models.PodConfig(
            name='test-pod',
            version='0.0.1',
            apps=self.sample_config.apps,
            images=[models.PodConfig.Image(tag='no-such-tag')],
        )
        with self.assertRaisesRegex(AssertionError, r'expect non-None value'):
            list_image_ids(config)

    #
    # Dependent images.
    #

    def test_add_ref_image_ids(self):

        def list_image_ids():
            return sorted(
                p.name for p in \
                pods._get_deps_path(self.sample_pod_dir_path).iterdir()
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

        config = models.PodConfig(
            name='test-pod',
            version='0.0.1',
            apps=self.sample_config.apps,
            images=[
                models.PodConfig.Image(id=image_id_1),
                models.PodConfig.Image(id=image_id_2),
            ],
        )

        new_config = pods._add_ref_image_ids(self.sample_pod_dir_path, config)
        self.assertEqual(config, new_config)
        self.assertEqual(list_image_ids(), [image_id_1, image_id_2])
        self.assertEqual(
            images._get_ref_count(images.get_image_dir_path(image_id_1)), 2
        )
        self.assertEqual(
            images._get_ref_count(images.get_image_dir_path(image_id_2)), 2
        )

    def test_iter_ref_image_ids(self):

        def list_ref_image_ids(pod_dir_path):
            return sorted(pods._iter_ref_image_ids(pod_dir_path))

        image_id_1 = self.make_image_id(1)
        image_id_2 = self.make_image_id(2)
        self.create_pod_dir(self.sample_pod_id, self.sample_config)
        self.create_image_dir(image_id_1, self.sample_metadata)
        self.create_image_dir(image_id_2, self.sample_metadata)
        self.assertEqual(list_ref_image_ids(self.sample_pod_dir_path), [])

        pods._add_ref_image_ids(
            self.sample_pod_dir_path,
            models.PodConfig(
                name='test-pod',
                version='0.0.1',
                apps=self.sample_config.apps,
                images=[
                    models.PodConfig.Image(id=image_id_1),
                    models.PodConfig.Image(id=image_id_2),
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
            pods._get_pod_status(self.sample_pod_dir_path, self.sample_config),
            {},
        )

        self.create_pod_dir(self.sample_pod_id, self.sample_config)
        app = self.sample_config.apps[0]
        path = builders._get_pod_app_exit_status_path(
            pods._get_rootfs_path(self.sample_pod_dir_path), app
        )
        path.parent.mkdir(parents=True)
        path.write_text('99')
        pod_status = pods._get_pod_status(
            self.sample_pod_dir_path, self.sample_config
        )
        self.assertEqual(list(pod_status.keys()), [app.name])
        self.assertEqual(pod_status[app.name][0], 99)

    def test_get_last_updated(self):
        self.assertIsNone(pods._get_last_updated({}))
        self.assertEqual(
            pods._get_last_updated({
                'app-1': (0, datetime.datetime(2001, 1, 1)),
            }),
            datetime.datetime(2001, 1, 1),
        )
        self.assertEqual(
            pods._get_last_updated({
                'app-1': (0, datetime.datetime(2001, 1, 1)),
                'app-2': (0, datetime.datetime(2002, 1, 1)),
            }),
            datetime.datetime(2002, 1, 1),
        )

    #
    # Helpers for mount/umount.
    #

    def test_umount(self):
        path1 = pods._get_pod_repo_path() / 'some-file'
        path2 = pods._get_pod_repo_path() / 'some-dir'
        path3 = pods._get_pod_repo_path() / 'link-to-dir'
        path1.touch()
        path2.mkdir()
        path3.symlink_to(path2)
        pods._umount(path1)
        pods._umount(path2)
        with self.assertRaisesRegex(AssertionError, r'expect not.*is_symlink'):
            pods._umount(path3)


if __name__ == '__main__':
    unittest.main()
