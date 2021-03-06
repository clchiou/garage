import unittest

from pathlib import Path

import foreman

from garage import scripts

from templates import py

from tests.fixtures import PrepareForeman


class PyTest(PrepareForeman, unittest.TestCase):

    def test_define_package(self):
        py.define_package('some_pkg')

        label = foreman.Label.parse('//path/to/rules:copy_src')
        copy_src = self.loader.rules[label]

        label = foreman.Label.parse('//path/to/rules:build')
        build = self.loader.rules[label]

        label = foreman.Label.parse('//path/to/rules:tapeout')
        tapeout = self.loader.rules[label]

        parameters = {
            '//base:root': Path('/path/to/root'),
            '//base:drydock': Path('/path/to/drydock'),
            '//base:drydock/rootfs': Path('/path/to/drydock/rootfs'),
            '//py/cpython:pip': Path('pip'),
            '//py/cpython:modules': Path('/path/to/modules'),
            'src': Path('/path/to/src'),
        }
        with scripts.dry_run(), scripts.recording_commands() as cmds:
            copy_src.build(parameters)
            msg = r'package does not seem to be installed: some_pkg'
            with self.assertRaisesRegex(RuntimeError, msg):
                build.build(parameters)
            tapeout.build(parameters)

        # Match command sequence (probably very fragile)
        self.assertEqual(
            (
                ['mkdir', '--parents', '/path/to/drydock/path/to/rules'],
                ['rsync'],
                ['pip', 'install', '--no-deps'],
                #['rsync']
            ),
            (
                cmds[0][0:3],
                cmds[1][0:1],
                cmds[2][3:6],
                #cmds[3][3:4],  # Empty dirs so no call to rsync
            ),
        )

    def test_define_pip_package(self):
        py.define_pip_package('some_pkg', '0.0.1')

        label = foreman.Label.parse('//path/to/rules:build')
        build = self.loader.rules[label]

        label = foreman.Label.parse('//path/to/rules:tapeout')
        tapeout = self.loader.rules[label]

        parameters = {
            '//base:drydock/rootfs': Path('/path/to/drydock/rootfs'),
            '//py/cpython:pip': Path('pip'),
            '//py/cpython:modules': Path('/path/to/modules'),
        }
        with scripts.dry_run(), scripts.recording_commands() as cmds:
            build.build(parameters)
            tapeout.build(parameters)

        # Match command sequence (probably very fragile)
        self.assertEqual(
            (
                ['pip', 'install', 'some_pkg==0.0.1'],
                #['rsync']
            ),
            (
                cmds[0][2:5],
                #cmds[1][2:3],  # Empty dirs so no call to rsync
            ),
        )


if __name__ == '__main__':
    unittest.main()
