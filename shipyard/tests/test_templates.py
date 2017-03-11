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

        templates.define_archive(
            'cpython', derive_dst_path=None, **expect)

        label = foreman.Label.parse('//path/to/rules:cpython/archive_info')
        archive_info = self.loader.parameters[label].default
        self.assertEqual(expect, archive_info._asdict())

        label = foreman.Label.parse(
            '//path/to/rules:cpython/archive_destination')
        self.assertIn(label, self.loader.parameters)

        label = foreman.Label.parse('//path/to/rules:cpython/download')
        download = self.loader.rules[label]

        parameters = {
            'cpython/archive_info': archive_info,
            'cpython/archive_destination': Path('/path/to/somethere'),
        }
        with scripts.dry_run(), scripts.recording_commands() as cmds:
            download.build(parameters)

        # Match command sequence (probably very fragile)
        self.assertEqual('mkdir', cmds[0][0])
        self.assertEqual('wget', cmds[1][0])
        self.assertEqual(['tar', '--extract'], cmds[2][0:2])

    def test_define_package_common(self):
        templates.define_package_common(
            'cpython', derive_src_path=1, derive_drydock_src_path=2)

        label = foreman.Label.parse('//path/to/rules:cpython/src')
        self.assertEqual(1, self.loader.parameters[label].derive)

        label = foreman.Label.parse('//path/to/rules:cpython/drydock_src')
        self.assertEqual(2, self.loader.parameters[label].derive)


if __name__ == '__main__':
    unittest.main()
