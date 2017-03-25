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
        check_call(['sudo', 'cp', '/bin/echo', '/usr/local/bin/systemctl'])

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

    # `ops pods` commands and other helpers.

    def list_pods(self):
        output = check_output(
            ['python3', '-m', 'ops', 'pods', 'list', '-v'],
            cwd=str(self.root_path),
        )
        output = output.decode('ascii').split('\n')
        return list(filter(None, map(str.strip, output)))

    def is_deployed(self, pod_name):
        cmd = ['python3', '-m', 'ops', 'pods', 'is-deployed', '-v', pod_name]
        return call(cmd, cwd=str(self.root_path)) == 0

    def list_ports(self):
        output = check_output(
            ['python3', '-m', 'ops', 'ports', 'list', '-v'],
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
        cmd = ['python3', '-m', 'ops', 'pods', 'deploy', '-v', str(pod_file)]
        check_call(cmd, cwd=str(self.root_path))

    def start(self, tag):
        cmd = ['python3', '-m', 'ops', 'pods', 'start', '-v', tag]
        check_call(cmd, cwd=str(self.root_path))

    def stop(self, tag):
        cmd = ['python3', '-m', 'ops', 'pods', 'stop', '-v', tag]
        check_call(cmd, cwd=str(self.root_path))

    def undeploy(self, pod_file):
        cmd = ['python3', '-m', 'ops', 'pods', 'undeploy', '-v', str(pod_file)]
        check_call(cmd, cwd=str(self.root_path))
