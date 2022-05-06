import unittest
import unittest.mock

import distutils.errors

from g1.devtools import buildtools


class BuildtoolsTest(unittest.TestCase):

    @unittest.mock.patch(buildtools.__name__ + '.distutils.file_util')
    def test_make_copy_files(self, mock_file_util):
        mock_cmd = unittest.mock.Mock()
        mock_cmd.FILENAMES = []
        mock_cmd.SRC_DIR = None
        mock_cmd.DST_DIR = None
        cls = buildtools.make_copy_files(filenames=[])

        cls.initialize_options(mock_cmd)
        self.assertIsNone(mock_cmd.src_dir)
        self.assertIsNone(mock_cmd.dst_dir)

        with self.assertRaisesRegex(
            distutils.errors.DistutilsOptionError,
            r'--src-dir is required',
        ):
            cls.finalize_options(mock_cmd)

        mock_cmd.src_dir = 'a/b'
        with self.assertRaisesRegex(
            distutils.errors.DistutilsOptionError,
            r'--dst-dir is required',
        ):
            cls.finalize_options(mock_cmd)

        mock_cmd.dst_dir = 'c/d'
        mock_cmd.FILENAMES = ['e', 'f']
        with self.assertRaisesRegex(
            distutils.errors.DistutilsOptionError,
            r'source file does not exist: a/b/e',
        ):
            cls.finalize_options(mock_cmd)

        mock_file_util.copy_file.assert_not_called()
        cls.run(mock_cmd)
        self.assertEqual(
            mock_file_util.copy_file.mock_calls,
            [
                unittest.mock.call('a/b/e', 'c/d/e', preserve_mode=False),
                unittest.mock.call('a/b/f', 'c/d/f', preserve_mode=False),
            ],
        )

    @unittest.mock.patch(buildtools.__name__ + '.subprocess')
    def test_read_pkg_config(self, subprocess_mock):
        subprocess_mock.run.return_value.stdout = (
            b'-I"/s o m e/where/include" -I"/s o m e/where/include" '
            b'-L"/s o m e/where/lib" -L"/s o m e/where/lib" '
            b'-lfoo -lfoo '
            b'-DMSG="hello world" -DMSG="hello world" '
        )
        self.assertEqual(
            buildtools.read_package_config(''),
            buildtools.PackageConfig(
                include_dirs=['/s o m e/where/include'],
                library_dirs=['/s o m e/where/lib'],
                libraries=['foo'],
                extra_compile_args=['-DMSG=hello world'],
            ),
        )


if __name__ == '__main__':
    unittest.main()
