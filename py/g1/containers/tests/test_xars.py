import unittest
import unittest.mock

from pathlib import Path

from g1.containers import bases
from g1.containers import images
from g1.containers import xars
from g1.texts import jsons

try:
    from g1.devtools.tests import filelocks
except ImportError:
    filelocks = None

from tests import fixtures


class XarsTest(
    fixtures.TestCaseBase,
    filelocks.Fixture if filelocks else object,
):

    sample_xar_name = 'foo.sh'

    sample_exec_relpath = Path('a/b/c/foo.sh')

    sample_image_id = '0123456789abcdef' * 4

    sample_metadata = images.ImageMetadata(
        name='sample-app',
        version='1.0',
    )

    def setUp(self):
        super().setUp()
        self.xar_runner_script_dir_path = self.test_repo_path / 'runner-bin'
        self.xar_runner_script_dir_path.mkdir()
        bases.PARAMS.xar_runner_script_directory.unsafe_set(
            self.xar_runner_script_dir_path
        )
        bases.cmd_init()
        images.cmd_init()
        xars.cmd_init()
        self.sample_xar_dir_path = xars._get_xar_dir_path(self.sample_xar_name)
        self.sample_xar_runner_script_path = (
            self.xar_runner_script_dir_path / self.sample_xar_name
        )
        self.sample_image_dir_path = images.get_image_dir_path(
            self.sample_image_id
        )

    @staticmethod
    def make_image_id(id_int):
        return '%064d' % id_int

    @staticmethod
    def create_image_dir(image_id, metadata, exec_relpath):
        image_dir_path = images.get_image_dir_path(image_id)
        image_dir_path.mkdir()
        jsons.dump_dataobject(
            metadata,
            images._get_metadata_path(image_dir_path),
        )
        rootfs_path = images.get_rootfs_path(image_dir_path)
        (rootfs_path / exec_relpath.parent).mkdir(parents=True)
        (rootfs_path / exec_relpath).touch()

    @staticmethod
    def list_xar_dir_paths():
        return sorted(p.name for p in xars._iter_xar_dir_paths())

    def list_ref_image_ids(self):
        return sorted(xars._iter_ref_image_ids(self.sample_xar_dir_path))

    def has_ref_image_id(self, image_id):
        return xars._has_ref_image_id(self.sample_xar_dir_path, image_id)

    def add_ref_image_id(self, image_id):
        xars._add_ref_image_id(self.sample_xar_dir_path, image_id)

    def maybe_remove_ref_image_id(self, image_id):
        return xars._maybe_remove_ref_image_id(
            self.sample_xar_dir_path, image_id
        )

    def install_sample(self):
        self.create_image_dir(
            self.sample_image_id,
            self.sample_metadata,
            self.sample_exec_relpath,
        )
        xars.cmd_install(
            image_id=self.sample_image_id,
            xar_name=self.sample_xar_name,
            exec_relpath=self.sample_exec_relpath,
        )

    #
    # Data type.
    #

    def test_validate(self):
        for xar_name in (
            'hello-world',
            '01_23.sh',
        ):
            self.assertEqual(xars.validate_name(xar_name), xar_name)
            self.assertEqual(xars.validate_name(xar_name), xar_name)
        for invalid_xar_name in (
            '',
            'a/b',
        ):
            with self.assertRaisesRegex(
                AssertionError, r'expect .*fullmatch.*'
            ):
                xars.validate_name(invalid_xar_name)

    #
    # Top-level commands.
    #

    def test_cmd_install(self):
        self.create_image_dir(
            self.sample_image_id,
            self.sample_metadata,
            self.sample_exec_relpath,
        )
        self.assertEqual(self.list_xar_dir_paths(), [])

        image_id_1 = self.make_image_id(1)
        pattern = r'expect.*is_file.*images/trees/%s/metadata' % image_id_1
        with self.assertRaisesRegex(AssertionError, pattern):
            xars.cmd_install(
                image_id=image_id_1,
                xar_name=self.sample_xar_name,
                exec_relpath=self.sample_exec_relpath,
            )
        self.assertEqual(self.list_xar_dir_paths(), [])

        xars.cmd_install(
            name=self.sample_metadata.name,
            version=self.sample_metadata.version,
            xar_name=self.sample_xar_name,
            exec_relpath=self.sample_exec_relpath,
        )
        self.assertEqual(self.list_xar_dir_paths(), [self.sample_xar_name])

        with self.assertRaisesRegex(AssertionError, r'expect non-None value'):
            xars.cmd_install(
                name='no-such-name',
                version='no-such-version',
                xar_name=self.sample_xar_name,
                exec_relpath=self.sample_exec_relpath,
            )

    def test_cmd_list(self):
        self.assertEqual(list(xars.cmd_list()), [])

        self.install_sample()
        self.assertEqual(
            list(xars.cmd_list()),
            [{
                'xar': self.sample_xar_name,
                'id': self.sample_image_id,
                'name': self.sample_metadata.name,
                'version': self.sample_metadata.version,
                'exec': self.sample_exec_relpath,
                'active': False,
            }],
        )

    @unittest.skipUnless(filelocks, 'g1.tests.filelocks unavailable')
    @unittest.mock.patch(xars.__name__ + '.os')
    def test_cmd_exec(self, os_mock):
        with self.assertRaisesRegex(AssertionError, r'expect.*is_dir.*foo.sh'):
            xars.cmd_exec(self.sample_xar_name, [])
        os_mock.execv.assert_not_called()
        os_mock.execv.reset_mock()

        self.install_sample()
        exec_abspath = xars._get_exec_path(self.sample_xar_dir_path).resolve()

        xars.cmd_exec(self.sample_xar_name, ['1', '2', '3'])
        os_mock.execv.assert_called_once_with(
            str(exec_abspath), [self.sample_xar_name, '1', '2', '3']
        )
        os_mock.execv.reset_mock()

        with self.using_shared(
            xars._get_ref_path(self.sample_xar_dir_path, self.sample_image_id)
        ):
            xars.cmd_uninstall(self.sample_xar_name)

        with self.assertRaisesRegex(AssertionError, r'expect.*exists.*foo.sh'):
            xars.cmd_exec(self.sample_xar_name, ['4', '5', '6'])
        os_mock.execv.assert_not_called()
        os_mock.execv.reset_mock()

    @unittest.skipUnless(filelocks, 'g1.tests.filelocks unavailable')
    def test_cmd_uninstall(self):
        self.assertEqual(self.list_xar_dir_paths(), [])

        exec_path = xars._get_exec_path(self.sample_xar_dir_path)
        self.install_sample()
        self.assertTrue(exec_path.exists())
        self.assertEqual(self.list_xar_dir_paths(), [self.sample_xar_name])
        self.assertTrue(self.sample_xar_runner_script_path.exists())

        with self.using_shared(
            xars._get_ref_path(self.sample_xar_dir_path, self.sample_image_id)
        ):
            xars.cmd_uninstall(self.sample_xar_name)
        self.assertFalse(exec_path.exists())
        self.assertEqual(self.list_xar_dir_paths(), [self.sample_xar_name])
        self.assertFalse(self.sample_xar_runner_script_path.exists())

        xars.cmd_uninstall(self.sample_xar_name)
        self.assertFalse(exec_path.exists())
        self.assertEqual(self.list_xar_dir_paths(), [])
        self.assertFalse(self.sample_xar_runner_script_path.exists())

        # Okay to remove non-existent xar.
        xars.cmd_uninstall(self.sample_xar_name)
        self.assertFalse(exec_path.exists())
        self.assertEqual(self.list_xar_dir_paths(), [])
        self.assertFalse(self.sample_xar_runner_script_path.exists())

    @unittest.skipUnless(filelocks, 'g1.tests.filelocks unavailable')
    def test_cmd_cleanup(self):
        self.assertEqual(self.list_xar_dir_paths(), [])

        exec_path = xars._get_exec_path(self.sample_xar_dir_path)
        self.install_sample()
        self.assertTrue(exec_path.exists())
        self.assertEqual(self.list_xar_dir_paths(), [self.sample_xar_name])
        self.assertTrue(self.sample_xar_runner_script_path.exists())

        xars.cmd_cleanup()
        self.assertEqual(self.list_xar_dir_paths(), [self.sample_xar_name])
        self.assertTrue(self.sample_xar_runner_script_path.exists())

        with self.using_shared(
            xars._get_ref_path(self.sample_xar_dir_path, self.sample_image_id)
        ):
            xars.cmd_uninstall(self.sample_xar_name)
        self.assertEqual(self.list_xar_dir_paths(), [self.sample_xar_name])
        self.assertFalse(self.sample_xar_runner_script_path.exists())

        xars.cmd_cleanup()
        self.assertEqual(self.list_xar_dir_paths(), [])
        self.assertFalse(self.sample_xar_runner_script_path.exists())

    #
    # Repo layout.
    #

    def test_repo_layout(self):
        for actual, expect in (
            (
                xars._get_xars_repo_path(),
                bases.get_repo_path() / 'xars',
            ),
            (
                xars._get_xar_dir_path('foo.sh'),
                xars._get_xars_repo_path() / 'foo.sh',
            ),
            (
                xars._get_name(xars._get_xar_dir_path('foo.sh')),
                'foo.sh',
            ),
            (
                xars._get_deps_path(xars._get_xar_dir_path('foo.sh')),
                xars._get_xar_dir_path('foo.sh') / 'deps',
            ),
            (
                xars._get_ref_path(
                    xars._get_xar_dir_path('foo.sh'),
                    self.sample_image_id,
                ),
                xars._get_deps_path(xars._get_xar_dir_path('foo.sh')) /
                self.sample_image_id,
            ),
            (
                xars._get_exec_path(xars._get_xar_dir_path('foo.sh')),
                xars._get_xar_dir_path('foo.sh') / 'exec',
            ),
            (
                xars._get_image_rootfs_abspath(self.sample_image_id),
                images.get_rootfs_path(self.sample_image_dir_path),
            ),
            (
                xars._get_xar_runner_script_path('foo.sh'),
                self.xar_runner_script_dir_path / 'foo.sh',
            ),
        ):
            self.assertEqual(actual, expect)

        exec_abspath = xars._get_exec_path(self.sample_xar_dir_path).absolute()
        with self.assertRaisesRegex(ValueError, r' does not start with '):
            xars._get_exec_relpath(exec_abspath, self.sample_image_id)
        with self.assertRaisesRegex(ValueError, r' does not start with '):
            xars._get_image_id(exec_abspath)

        self.install_sample()

        exec_abspath = xars._get_exec_path(self.sample_xar_dir_path).resolve()
        self.assertEqual(
            xars._get_exec_relpath(exec_abspath, self.sample_image_id),
            self.sample_exec_relpath,
        )
        self.assertEqual(
            xars._get_image_id(exec_abspath),
            self.sample_image_id,
        )
        exec_target = xars._get_exec_target(
            self.sample_image_id, self.sample_exec_relpath
        )
        self.assertEqual(
            exec_target,
            Path('../../images/trees') / self.sample_image_id / 'rootfs' /
            self.sample_exec_relpath,
        )
        self.assertTrue((self.sample_xar_dir_path / exec_target).exists())

    #
    # Xar directories.
    #

    def test_iter_xar_dir_paths(self):
        self.create_image_dir(
            self.sample_image_id,
            self.sample_metadata,
            self.sample_exec_relpath,
        )

        self.assertEqual(self.list_xar_dir_paths(), [])
        self.assertEqual(images._get_ref_count(self.sample_image_dir_path), 1)

        xars._install_xar_dir(
            xars._get_xar_dir_path('foo.sh'),
            self.sample_image_id,
            self.sample_exec_relpath,
        )
        self.assertEqual(self.list_xar_dir_paths(), ['foo.sh'])
        self.assertEqual(images._get_ref_count(self.sample_image_dir_path), 2)

        xars._install_xar_dir(
            xars._get_xar_dir_path('bar.sh'),
            self.sample_image_id,
            self.sample_exec_relpath,
        )
        self.assertEqual(self.list_xar_dir_paths(), ['bar.sh', 'foo.sh'])
        self.assertEqual(images._get_ref_count(self.sample_image_dir_path), 3)

    #
    # Xar directory.
    #

    def test_xar_dir(self):

        def assert_absent():
            self.assertFalse(self.sample_xar_dir_path.exists())
            self.assertFalse(self.sample_xar_runner_script_path.exists())
            self.assertEqual(images._get_ref_count(image_dir_path_1), 1)
            self.assertEqual(images._get_ref_count(image_dir_path_2), 1)

        def assert_present(current_image_id, image_ids):
            self.assertTrue(self.sample_xar_dir_path.exists())
            self.assertEqual(
                xars._get_exec_path(self.sample_xar_dir_path).resolve(),
                images.get_rootfs_path(
                    images.get_image_dir_path(current_image_id)
                ) / self.sample_exec_relpath,
            )
            self.assertEqual(self.list_ref_image_ids(), image_ids)
            self.assertTrue(self.sample_xar_runner_script_path.exists())
            self.assertEqual(
                images._get_ref_count(image_dir_path_1),
                2 if image_id_1 in image_ids else 1,
            )
            self.assertEqual(
                images._get_ref_count(image_dir_path_2),
                2 if image_id_2 in image_ids else 1,
            )

        def install_xar_dir(image_id):
            xars._install_xar_dir(
                self.sample_xar_dir_path, image_id, self.sample_exec_relpath
            )

        image_id_1 = self.make_image_id(1)
        image_dir_path_1 = images.get_image_dir_path(image_id_1)
        self.create_image_dir(
            image_id_1,
            self.sample_metadata,
            self.sample_exec_relpath,
        )
        image_id_2 = self.make_image_id(2)
        image_dir_path_2 = images.get_image_dir_path(image_id_2)
        self.create_image_dir(
            image_id_2,
            self.sample_metadata,
            self.sample_exec_relpath,
        )
        image_id_3 = self.make_image_id(3)
        pattern = r'expect.*is_file.*images/trees/%s/metadata' % image_id_3

        assert_absent()

        with self.assertRaisesRegex(AssertionError, pattern):
            install_xar_dir(image_id_3)
        assert_absent()

        install_xar_dir(image_id_1)
        assert_present(image_id_1, [image_id_1])

        with self.assertRaisesRegex(AssertionError, pattern):
            install_xar_dir(image_id_3)
        assert_present(image_id_1, [image_id_1])

        install_xar_dir(image_id_2)
        assert_present(image_id_2, [image_id_1, image_id_2])

        with self.assertRaisesRegex(AssertionError, pattern):
            install_xar_dir(image_id_3)
        assert_present(image_id_2, [image_id_1, image_id_2])

        install_xar_dir(image_id_1)
        assert_present(image_id_1, [image_id_1, image_id_2])

        with self.assertRaisesRegex(AssertionError, pattern):
            install_xar_dir(image_id_3)
        assert_present(image_id_1, [image_id_1, image_id_2])

        xars._cleanup_xar_dir(self.sample_xar_dir_path)
        assert_present(image_id_1, [image_id_1])

        xars._remove_xar_dir(self.sample_xar_dir_path)
        assert_absent()

    #
    # Dependent images.
    #

    @unittest.skipUnless(filelocks, 'g1.tests.filelocks unavailable')
    def test_ref_image_ids(self):
        image_id_1 = self.make_image_id(1)
        self.create_image_dir(
            image_id_1,
            self.sample_metadata,
            self.sample_exec_relpath,
        )
        image_id_2 = self.make_image_id(2)
        self.create_image_dir(
            image_id_2,
            self.sample_metadata,
            self.sample_exec_relpath,
        )

        xars._install_xar_dir(
            self.sample_xar_dir_path,
            image_id_1,
            self.sample_exec_relpath,
        )
        self.assertEqual(self.list_ref_image_ids(), [image_id_1])
        self.assertTrue(self.has_ref_image_id(image_id_1))
        self.assertFalse(self.has_ref_image_id(image_id_2))

        self.add_ref_image_id(image_id_2)
        self.assertEqual(self.list_ref_image_ids(), [image_id_1, image_id_2])
        self.assertTrue(self.has_ref_image_id(image_id_1))
        self.assertTrue(self.has_ref_image_id(image_id_2))

        self.assertTrue(self.maybe_remove_ref_image_id(image_id_1))
        self.assertEqual(self.list_ref_image_ids(), [image_id_2])
        self.assertFalse(self.has_ref_image_id(image_id_1))
        self.assertTrue(self.has_ref_image_id(image_id_2))

        with self.using_shared(
            xars._get_ref_path(self.sample_xar_dir_path, image_id_2)
        ):
            self.assertFalse(self.maybe_remove_ref_image_id(image_id_2))
        self.assertEqual(self.list_ref_image_ids(), [image_id_2])
        self.assertFalse(self.has_ref_image_id(image_id_1))
        self.assertTrue(self.has_ref_image_id(image_id_2))


if __name__ == '__main__':
    unittest.main()
