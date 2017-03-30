"""Integration test fixture."""

__all__ = [
    'Fixture',
]

import getpass
import unittest
from pathlib import Path
from subprocess import call, check_call, check_output


class Fixture:

    @staticmethod
    def inside_container(cls):
        cond = getpass.getuser() == 'plumber'
        return unittest.skipUnless(cond, 'not inside container')(cls)

    @classmethod
    def setUpClass(cls):
        # Make sure we are inside a container
        assert getpass.getuser() == 'plumber'

        # Ensure paths.
        cls.root_path = Path(__file__).parent.parent
        assert (cls.root_path / 'ops').is_dir()
        cls.testdata_path = Path(__file__).parent / 'testdata'
        assert cls.testdata_path.is_dir()

        # Install the fake systemctl because you can't run systemd in a
        # Docker container (can you?)
        check_call(['sudo', 'cp', '/bin/true', '/usr/local/bin/systemctl'])

    @classmethod
    def tearDownClass(cls):
        # Uninstall the fake systemctl
        check_call(['sudo', 'rm', '/usr/local/bin/systemctl'])

    # Helper methods.

    def assertDir(self, path):
        self.assertTrue(Path(path).is_dir())

    def assertNotDir(self, path):
        self.assertFalse(Path(path).is_dir())

    def assertFile(self, path):
        self.assertTrue(Path(path).is_file())

    def assertNotFile(self, path):
        self.assertFalse(Path(path).is_file())

    def assertImage(self, target_image_id):
        self.assertTrue(self.match_image(target_image_id))

    def assertNotImage(self, target_image_id):
        self.assertFalse(self.match_image(target_image_id))

    def assertEqualContents(self, expect, actual):
        self.assertEqual(Path(expect).read_text(), Path(actual).read_text())

    # `ops-onboard pods` commands and other helpers.

    OPS_CMD = ['python3', '-m', 'ops.onboard', '-v']

    def list_pods(self):
        output = check_output(
            self.OPS_CMD + ['pods', 'list'],
            cwd=str(self.root_path),
        )
        output = output.decode('ascii').split('\n')
        return list(filter(None, map(str.strip, output)))

    def is_undeployed(self, pod_name):
        cmd = self.OPS_CMD + ['pods', 'is-undeployed', pod_name]
        return call(cmd, cwd=str(self.root_path)) == 0

    def is_deployed(self, pod_name):
        # Because we mock out systemctl, pod state cannot be detected
        # correctly
        return not self.is_undeployed(pod_name)

    def list_ports(self):
        output = check_output(
            self.OPS_CMD + ['ports', 'list'],
            cwd=str(self.root_path),
        )
        output = output.decode('ascii').split('\n')
        return list(filter(None, map(str.strip, output)))

    def list_images(self):
        output = check_output(
            ['rkt', 'image', 'list', '--fields=id', '--full', '--no-legend'])
        output = output.decode('ascii').split('\n')
        return list(filter(None, map(str.strip, output)))

    def match_image(self, target_image_id):
        for image_id in self.list_images():
            if (image_id.startswith(target_image_id) or
                    target_image_id.startswith(image_id)):
                return True
        return False

    def deploy(self, pod_file):
        cmd = self.OPS_CMD + ['pods', 'deploy', str(pod_file)]
        check_call(cmd, cwd=str(self.root_path))

    def start(self, tag):
        # Use `--force` because we mock out systemctl and thus pod state
        # cannot be detected correctly
        cmd = self.OPS_CMD + ['pods', 'start', '--force', tag]
        check_call(cmd, cwd=str(self.root_path))

    def stop(self, tag):
        cmd = self.OPS_CMD + ['pods', 'stop', tag]
        check_call(cmd, cwd=str(self.root_path))

    def undeploy(self, pod_file):
        cmd = self.OPS_CMD + ['pods', 'undeploy', str(pod_file)]
        check_call(cmd, cwd=str(self.root_path))
