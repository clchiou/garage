import unittest

import subprocess
import tarfile
import tempfile
from pathlib import Path

from templates import volumes


class VolumesTest(unittest.TestCase):

    def test_fill_tarball(self):
        with tempfile.NamedTemporaryFile() as temp_tar:
            self.do_test_fill_tarball(temp_tar.name)

    def do_test_fill_tarball(self, tarball_path):

        parameters = {
            'testdata': Path(__file__).parent / 'testdata',
        }

        # 2000-01-02 03:04
        mtime = 946800240

        # Test case: empty spec.

        spec = {
            'members': [
            ],
        }
        with tarfile.open(tarball_path, 'w') as tarball:
            volumes.fill_tarball(parameters, spec, tarball)

        self.assertEqual(
            b'',
            self._list_tarball(tarball_path),
        )

        # Test case: in-place content.

        spec = {
            'members': [
                {
                    'path': 'tmp',
                    'mode': 0o1777,
                    'mtime': mtime,
                    'kind': 'dir',
                    'uid': 0,
                    'gid': 0,
                },
                {
                    'path': 'tmp/foo.txt',
                    'mode': 0o644,
                    'mtime': mtime,
                    'kind': 'file',
                    'owner': 'nobody',
                    'group': 'nogroup',
                },
                {
                    'path': 'bar.txt',
                    'mode': 0o600,
                    'mtime': mtime,
                    'kind': 'file',
                    'owner': 'nobody',
                    'group': 'nogroup',
                    'content': 'hello world',
                },
            ],
        }
        with tarfile.open(tarball_path, 'w') as tarball:
            volumes.fill_tarball(parameters, spec, tarball)

        self.assertEqual(
            (b'drwxrwxrwt root/root         0 2000-01-02 03:04 tmp/\n'
             b'-rw-r--r-- nobody/nogroup    0 2000-01-02 03:04 tmp/foo.txt\n'
             b'-rw------- nobody/nogroup   11 2000-01-02 03:04 bar.txt\n'),
            self._list_tarball(tarball_path),
        )

        # Test case: content_path_parameter.

        spec = {
            'members': [
                {
                    'path': '.',
                    'owner': 'nobody',
                    'group': 'nogroup',
                    'content_path_parameter': 'testdata',
                },
            ],
        }
        with tarfile.open(tarball_path, 'w') as tarball:
            volumes.fill_tarball(parameters, spec, tarball)

        self.assertRegex(
            self._list_tarball(tarball_path),
            (rb'drwxrwxr-x nobody/nogroup    0 \d\d\d\d-\d\d-\d\d \d\d:\d\d path/\n'
             rb'drwxrwxr-x nobody/nogroup    0 \d\d\d\d-\d\d-\d\d \d\d:\d\d path/to/\n'
             rb'drwxrwxr-x nobody/nogroup    0 \d\d\d\d-\d\d-\d\d \d\d:\d\d path/to/rules/\n'
             rb'-rw-rw-r-- nobody/nogroup   23 \d\d\d\d-\d\d-\d\d \d\d:\d\d path/to/rules/build.py\n'
             rb'-rw-rw-r-- nobody/nogroup    0 \d\d\d\d-\d\d-\d\d \d\d:\d\d path/to/rules/foo.service\n'),
        )

    @staticmethod
    def _list_tarball(tarball_path):
        return subprocess.check_output([
            'tar', '--list', '--verbose', '--file', tarball_path,
        ])


if __name__ == '__main__':
    unittest.main()
