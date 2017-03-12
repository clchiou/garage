import unittest

from pathlib import Path

import foreman

from garage import scripts

from templates import common, utils

if __name__ == '__main__':
    from fixtures import PrepareForeman
else:
    from .fixtures import PrepareForeman


class TemplatesTest(PrepareForeman, unittest.TestCase):

    def test_parse_common_args(self):

        expect = []
        actual = []

        @utils.parse_common_args
        def func(root: 'root', name: 'name'):
            actual.append((root, name))

        func(); expect.append(('//base:root', ''))
        func(root=None, name=None); expect.append(('//base:root', ''))
        func(root='', name=''); expect.append(('//base:root', ''))
        func(root='x', name='y'); expect.append(('x', 'y/'))
        func(root='x', name='z/'); expect.append(('x', 'z/'))

        self.assertEqual(expect, actual)

    def test_define_archive(self):
        expect = {
            'uri': 'https://www.python.org/ftp/python/3.5.1/Python-3.5.1.tar.xz',
            'filename': Path('Python-3.5.1.tar.xz'),
            'output': Path('Python-3.5.1'),
            'checksum': None,
        }

        common.define_archive(name='cpython', **expect)

        label = foreman.Label.parse('//path/to/rules:cpython/archive_info')
        archive_info = self.loader.parameters[label].default
        self.assertEqual(expect, archive_info._asdict())

        label = foreman.Label.parse('//path/to/rules:cpython/download')
        download = self.loader.rules[label]

        parameters = {
            '//base:drydock': Path('/somewhere'),
            'cpython/archive_info': archive_info,
        }
        with scripts.dry_run(), scripts.recording_commands() as cmds:
            download.build(parameters)

        # Match command sequence (probably very fragile)
        self.assertEqual('mkdir', cmds[0][0])
        self.assertEqual('wget', cmds[1][0])
        self.assertEqual(['tar', '--extract'], cmds[2][0:2])

    def test_define_package_common(self):
        copy_src = common.define_package_common(name='cpython')

        label = foreman.Label.parse('//path/to/rules:cpython/src')
        self.assertIn(label, self.loader.parameters)

        parameters = {
            '//base:drydock': Path('/somewhere'),
            'cpython/src': Path('/other/place'),
        }
        with scripts.dry_run(), scripts.recording_commands() as cmds:
            copy_src.build(parameters)

        # Match command sequence (probably very fragile)
        self.assertEqual('mkdir', cmds[0][0])
        self.assertEqual('rsync', cmds[1][0])


if __name__ == '__main__':
    unittest.main()
