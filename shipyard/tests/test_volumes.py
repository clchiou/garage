import unittest

import datetime
import subprocess
import tarfile
import tempfile
from pathlib import Path

from templates import filespecs
from templates import volumes


def apply_specs(specs, tarball):
    for spec in specs:
        spec = filespecs.make_filespec(spec)
        volumes.apply_filespec_to_tarball(spec, tarball)


class VolumesTest(unittest.TestCase):

    def test_apply_filespec_to_tarball(self):
        with tempfile.NamedTemporaryFile() as temp_tar:
            self.do_test_apply_filespec_to_tarball(temp_tar.name)

    def do_test_apply_filespec_to_tarball(self, tarball_path):

        mtime = int(datetime.datetime(2000, 1, 2, 3, 4).timestamp())

        # Test case: empty spec.

        with tarfile.open(tarball_path, 'w') as tarball:
            apply_specs([], tarball)

        self.assertEqual(
            b'',
            self._list_tarball(tarball_path),
        )

        # Test case: in-place content.

        specs = [
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
        ]
        with tarfile.open(tarball_path, 'w') as tarball:
            apply_specs(specs, tarball)

        self.assertEqual(
            (b'drwxrwxrwt root/root         0 2000-01-02 03:04 tmp/\n'
             b'-rw-r--r-- nobody/nogroup    0 2000-01-02 03:04 tmp/foo.txt\n'
             b'-rw------- nobody/nogroup   11 2000-01-02 03:04 bar.txt\n'),
            self._list_tarball(tarball_path),
        )

        # Test case: content_path.

        specs = [
            {
                'path': '.',
                'owner': 'nobody',
                'group': 'nogroup',
                'content_path': Path(__file__).parent / 'testdata',
            },
        ]
        with tarfile.open(tarball_path, 'w') as tarball:
            apply_specs(specs, tarball)

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
