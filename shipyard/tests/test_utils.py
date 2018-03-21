import unittest
import unittest.mock

import getpass
import subprocess
import tempfile
from pathlib import Path

from templates import utils


class UtilsTest(unittest.TestCase):

    @unittest.mock.patch('garage.scripts.using_sudo')
    def test_tapeout_filespecs(self, _):
        owner = group = getpass.getuser()
        with tempfile.TemporaryDirectory() as output_dir:
            utils.tapeout_filespecs(
                {
                    '//base:drydock/rootfs': Path(output_dir),
                },
                Path('.'),
                [
                    {
                        'path': 'foo.txt',
                        'kind': 'file',
                        'mode': 0o644,
                        'owner': owner,
                        'group': group,
                        'content': 'hello world',
                    },
                    {
                        'path': '.',
                        'mode': 0o755,
                        'content_path': Path(__file__).parent / 'testdata',
                    },
                ],
            )
            actual = subprocess.check_output(['find', output_dir])
            actual = sorted(filter(None, actual.decode('ascii').split('\n')))
        self.assertEqual(
            [
                output_dir,
                output_dir + '/foo.txt',
                output_dir + '/path',
                output_dir + '/path/to',
                output_dir + '/path/to/rules',
                output_dir + '/path/to/rules/build.py',
                output_dir + '/path/to/rules/foo.service',
            ],
            actual,
        )


if __name__ == '__main__':
    unittest.main()
