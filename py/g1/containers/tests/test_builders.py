import unittest

import time
from pathlib import Path

import g1.files
from g1.containers import builders
from g1.containers import models

from tests import fixtures


class BuildersTest(fixtures.TestCaseBase):

    def test_cmd_setup_base_rootfs(self):
        (self.test_repo_path / 'etc/default').mkdir(parents=True)
        etc_path = self.test_repo_path / 'etc/systemd/system'
        etc_path.mkdir(parents=True)
        lib_path = self.test_repo_path / 'usr/lib/systemd/system'
        lib_path.mkdir(parents=True)
        sbin_path = self.test_repo_path / 'usr/sbin'
        sbin_path.mkdir(parents=True)
        var_path = self.test_repo_path / 'var/cache'
        var_path.mkdir(parents=True)
        var_lib_path = self.test_repo_path / 'var/lib'
        var_lib_path.mkdir(parents=True)
        for unit in builders._BASE_UNITS:
            (lib_path / unit).touch()
        (etc_path / 'irrelevant-1').touch()
        (etc_path / 'irrelevant-2').mkdir()
        (lib_path / 'irrelevant-3').touch()
        (lib_path / 'irrelevant-4').mkdir()
        (var_path / 'irrelevant-5').touch()
        (var_path / 'irrelevant-6').mkdir()

        builders.cmd_setup_base_rootfs(self.test_repo_path, None)

        self.assertEqual(self.list_dir(var_path), [])

        self.assertEqual(
            (self.test_repo_path / 'etc/resolv.conf').read_text(),
            builders._RESOLV_CONF,
        )

        self.assertEqual(
            self.list_dir(etc_path),
            sorted(
                set(
                    Path(u.relpath).parts[0] for u in builders._ETC_UNIT_FILES
                )
            ),
        )
        self.assertEqual(
            self.list_dir(lib_path),
            sorted(
                set(
                    Path(u.relpath).parts[0] for u in builders._LIB_UNIT_FILES
                )
                | builders._BASE_UNITS
            ),
        )

        self.assertEqual(self.list_dir(sbin_path), ['pod-exit'])
        var_lib_pod_path = var_lib_path / 'pod'
        self.assertTrue(var_lib_pod_path.is_dir())
        self.assertTrue(self.list_dir(var_lib_pod_path), ['exit-status'])
        self.assertTrue((var_lib_pod_path / 'exit-status').is_dir())

    def test_generate_unit_file(self):
        etc_path = self.test_repo_path / 'etc/systemd/system'
        etc_path.mkdir(parents=True)
        pod_target_wants = etc_path / 'pod.target.wants'
        pod_target_wants.mkdir()
        link_path = pod_target_wants / 'hello-world.service'
        self.assertFalse(g1.files.lexists(link_path))
        unit_path = etc_path / 'hello-world.service'
        self.assertFalse(unit_path.exists())

        builders.generate_unit_file(
            self.test_repo_path,
            'some-pod',
            '0.0.1',
            models.PodConfig.App(
                name='hello-world',
                exec=['/bin/echo', '"hello world"'],
                user='root',
                group='root',
            ),
        )
        self.assertTrue(g1.files.lexists(link_path))
        self.assertTrue(link_path.samefile(unit_path))
        self.assertTrue(unit_path.exists())
        self.assertEqual(
            unit_path.read_text(),
            '[Unit]\n'
            'Conflicts=shutdown.target\n'
            'Before=pod.target shutdown.target\n'
            '\n'
            '[Service]\n'
            'Restart=no\n'
            'SyslogIdentifier=some-pod/hello-world@0.0.1\n'
            'ExecStart="/bin/echo" "\\"hello world\\""\n'
            'ExecStopPost=/usr/sbin/pod-exit "%n"\n'
            'LimitNOFILE=65536\n',
        )

        builders.generate_unit_file(
            self.test_repo_path,
            'some-other-pod',
            '0.0.1',
            models.PodConfig.App(
                name='hello-world-2',
                service_section='ExecStart=/bin/echo hello world',
            ),
        )
        self.assertEqual(
            (etc_path / 'hello-world-2.service').read_text(),
            '[Unit]\n'
            'Conflicts=shutdown.target\n'
            'Before=pod.target shutdown.target\n'
            '\n'
            '[Service]\n'
            'ExecStart=/bin/echo hello world\n',
        )

    def test_quote_arg(self):
        self.assertEqual(
            builders._quote_arg('\'hello$world%spam egg"'),
            '"\\\'hello$$world%%spam egg\\""',
        )

    def test_get_pod_app_exit_status(self):
        var_path = self.test_repo_path / 'var/lib/pod/exit-status'
        app = models.PodConfig.App(name='hello-world', exec=['/bin/echo'])
        self.assertEqual(
            builders.get_pod_app_exit_status(self.test_repo_path, app),
            (None, None),
        )

        var_path.mkdir(parents=True)
        self.assertEqual(
            builders.get_pod_app_exit_status(self.test_repo_path, app),
            (None, None),
        )

        status_path = var_path / 'hello-world.service'

        status_path.write_text('0\n')
        status, mtime0 = builders.get_pod_app_exit_status(
            self.test_repo_path, app
        )
        self.assertEqual(status, 0)

        time.sleep(0.01)

        status_path.write_text('1\n')
        status, mtime1 = builders.get_pod_app_exit_status(
            self.test_repo_path, app
        )
        self.assertEqual(status, 1)
        self.assertLess(mtime0, mtime1)


if __name__ == '__main__':
    unittest.main()
