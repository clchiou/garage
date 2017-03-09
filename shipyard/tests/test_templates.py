import unittest

from pathlib import Path

import foreman

from garage import scripts

import templates

if __name__ == '__main__':
    from fixtures import PrepareForeman
else:
    from .fixtures import PrepareForeman


class TemplatesTest(PrepareForeman, unittest.TestCase):

    def test_define_archive(self):
        expect = {
            'uri': 'https://www.python.org/ftp/python/3.5.1/Python-3.5.1.tar.xz',
            'filename': Path('Python-3.5.1.tar.xz'),
            'output': Path('Python-3.5.1'),
        }

        download = templates.define_archive(derive_dst_path=None, **expect)

        label = foreman.Label.parse('//path/to/rules:archive_info')
        archive_info = self.loader.parameters[label].default
        self.assertEqual(expect, archive_info._asdict())

        label = foreman.Label.parse('//path/to/rules:archive_destination')
        self.assertIn(label, self.loader.parameters)

        parameters = {
            'archive_info': archive_info,
            'archive_destination': Path('/path/to/somethere'),
        }
        with scripts.dry_run(), scripts.recording_commands() as cmds:
            download.build(parameters)

        # Match command sequence (probably very fragile)
        self.assertEqual('mkdir', cmds[0][0])
        self.assertEqual('wget', cmds[1][0])
        self.assertEqual(['tar', '--extract'], cmds[2][0:2])


if __name__ == '__main__':
    unittest.main()
