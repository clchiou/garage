import unittest
import unittest.mock

from g1.devtools import buildtools


class BuildtoolsTest(unittest.TestCase):

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
