import unittest
import unittest.mock

import os
import subprocess
from pathlib import Path

from g1.scripts import bases
from g1.scripts import commands


class CommandsTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        patch = unittest.mock.patch(bases.__name__ + '.subprocess')
        self.subprocess_mock = patch.start()

    def tearDown(self):
        unittest.mock.patch.stopall()
        super().tearDown()

    def assert_runs(self, *args_list):
        self.subprocess_mock.run.assert_has_calls([
            unittest.mock.call(
                args,
                capture_output=False,
                check=True,
                cwd=unittest.mock.ANY,
                input=None,
                env=None,
            ) for args in args_list
        ])

    def test_chown(self):
        commands.chown('foo', None, 'bar')
        self.assert_runs(['chown', 'foo', 'bar'])

    def test_cp(self):
        commands.cp('a', 'b')
        self.assert_runs(['cp', '--force', 'a', 'b'])

    def test_make_relative_symlink(self):
        commands.make_relative_symlink('/a/d/e', '/a/b/c')
        self.assert_runs(
            ['mkdir', '--parents', '/a/b'],
            ['ln', '--symbolic', '../d/e', 'c'],
        )

    def test_ln(self):
        commands.ln('a', 'b')
        self.assert_runs(['ln', '--symbolic', 'a', 'b'])

    def test_mkdir(self):
        commands.mkdir('a/b/c')
        self.assert_runs(['mkdir', '--parents', 'a/b/c'])

    def test_rm(self):
        commands.rm('a/b')
        commands.rm('p/q', recursive=True)
        self.assert_runs(
            ['rm', '--force', 'a/b'],
            ['rm', '--force', '--recursive', 'p/q'],
        )

    def test_rmdir(self):
        commands.rmdir('p/q')
        self.assert_runs(['rmdir', 'p/q'])

    def test_validate_checksum(self):
        self.subprocess_mock.run.return_value.returncode = 0
        commands.validate_checksum('foo', 'md5:123')
        commands.validate_checksum('baz', 'sha256:789')
        commands.validate_checksum('bar', 'sha512:456')
        self.subprocess_mock.run.assert_has_calls([
            unittest.mock.call(
                ['md5sum', '--check', '--status', '-'],
                capture_output=False,
                check=False,
                cwd=None,
                input=b'123 foo',
                env=None,
            ),
            unittest.mock.call(
                ['sha256sum', '--check', '--status', '-'],
                capture_output=False,
                check=False,
                cwd=None,
                input=b'789 baz',
                env=None,
            ),
            unittest.mock.call(
                ['sha512sum', '--check', '--status', '-'],
                capture_output=False,
                check=False,
                cwd=None,
                input=b'456 bar',
                env=None,
            ),
        ])

    def test_write_bytes(self):
        commands.write_bytes(b'bar', 'a/b/c')
        self.subprocess_mock.run.assert_called_once_with(
            ['tee', 'a/b/c'],
            capture_output=False,
            check=True,
            cwd=None,
            input=b'bar',
            env=None,
            stdout=subprocess.DEVNULL,
        )

    def test_extract(self):
        commands.extract('a/b/c.tgz')
        commands.extract('d/e/f.zip')
        self.assert_runs(
            ['tar', '--extract', '--file', 'a/b/c.tgz', '--gzip'],
            ['unzip', 'd/e/f.zip'],
        )
        with self.assertRaisesRegex(AssertionError, r'unknown archive type'):
            commands.extract('foo.gz')

    def test_tar_extract(self):
        commands.tar_extract('a/b/c.tgz')
        commands.tar_extract('p/q/r.tar', directory='f/g')
        self.assert_runs(
            ['tar', '--extract', '--file', 'a/b/c.tgz', '--gzip'],
            ['tar', '--extract', '--file', 'p/q/r.tar', '--directory', 'f/g'],
        )

    def test_unzip(self):
        commands.unzip('a/b/c.zip')
        commands.unzip('p/q/r.zip', directory='f/g')
        self.assert_runs(
            ['unzip', 'a/b/c.zip'],
            ['unzip', 'p/q/r.zip', '-d', 'f/g'],
        )

    def test_make(self):
        jobs = '--jobs=%d' % (os.cpu_count() + 2)
        commands.make()
        commands.make(['all', 'clean'])
        commands.make(['test'], num_jobs=99)
        self.assert_runs(
            ['make', jobs],
            ['make', jobs, 'all', 'clean'],
            ['make', '--jobs=99', 'test'],
        )

    def test_apt_get_update(self):
        commands.apt_get_update()
        self.assert_runs(['apt-get', '--assume-yes', 'update'])

    def test_apt_get_full_upgrade(self):
        commands.apt_get_full_upgrade()
        self.assert_runs(['apt-get', '--assume-yes', 'full-upgrade'])

    def test_apt_get_install(self):
        commands.apt_get_install(['p', 'q'])
        self.assert_runs(['apt-get', '--assume-yes', 'install', 'p', 'q'])

    def test_apt_get_clean(self):
        commands.apt_get_clean()
        self.assert_runs(['apt-get', '--assume-yes', 'clean'])

    def test_wget(self):
        url = 'http://x/y/z'
        headers = ('A=B', )
        commands.wget(url, headers=headers)
        self.assert_runs(['wget', '--no-verbose', '--header', 'A=B', url])

    def test_git_clone(self):
        url = 'http://x/y/z.git'
        cwd = Path.cwd()
        commands.git_clone(url)
        self.assert_runs(
            ['mkdir', '--parents', str(cwd)],
            ['git', 'clone', url, 'z'],
        )

    def test_git_clone_with_non_defaults(self):
        url = 'http://x/y/z.git'
        repo_path = '/a/b/c'
        treeish = '123'
        commands.git_clone(url, repo_path=repo_path, treeish=treeish)
        repo_path = Path(repo_path)
        self.assert_runs(
            ['mkdir', '--parents', str(repo_path.parent)],
            ['git', 'clone', url, repo_path.name],
            ['git', 'checkout', '123'],
        )


if __name__ == '__main__':
    unittest.main()
