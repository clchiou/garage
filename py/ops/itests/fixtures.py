"""Integration test fixture."""

__all__ = [
    'Fixture',
]

import getpass
import json
import sys
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

    @classmethod
    def tearDownClass(cls):
        pass  # Nothing here at the moment.

    # Helper methods.

    @property
    def systemd_enabled(self):
        path = Path('/tmp/ops_runner_state.json')
        if not path.exists():
            return set()
        return set(json.loads(path.read_text())['systemd_enabled'])

    @property
    def systemd_started(self):
        path = Path('/tmp/ops_runner_state.json')
        if not path.exists():
            return set()
        return set(json.loads(path.read_text())['systemd_started'])

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

    OPS_CMD = ['python3', '-m', 'itests.ops_runner', '-v']

    def list_pods(self):
        output = check_output(
            self.OPS_CMD + ['pods', 'list'],
            cwd=str(self.root_path),
        )
        output = output.decode('ascii').split('\n')
        return list(filter(None, map(str.strip, output)))

    def is_deployed(self, pod_name):
        cmd = self.OPS_CMD + ['pods', 'is-deployed', pod_name]
        return call(cmd, cwd=str(self.root_path)) == 0

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
        self._check_call(cmd, cwd=str(self.root_path))

    def enable(self, tag, *, extra_args=()):
        cmd = self.OPS_CMD + ['pods', 'enable', tag] + list(extra_args)
        self._check_call(cmd, cwd=str(self.root_path))

    def start(self, tag, *, extra_args=()):
        cmd = self.OPS_CMD + ['pods', 'start', tag] + list(extra_args)
        self._check_call(cmd, cwd=str(self.root_path))

    def stop(self, tag, *, extra_args=()):
        cmd = self.OPS_CMD + ['pods', 'stop', tag] + list(extra_args)
        self._check_call(cmd, cwd=str(self.root_path))

    def disable(self, tag, *, extra_args=()):
        cmd = self.OPS_CMD + ['pods', 'disable', tag] + list(extra_args)
        self._check_call(cmd, cwd=str(self.root_path))

    def undeploy(self, pod_file):
        cmd = self.OPS_CMD + ['pods', 'undeploy', str(pod_file)]
        self._check_call(cmd, cwd=str(self.root_path))

    @staticmethod
    def _check_call(cmd, *, cwd):
        print('exec: %s' % ' '.join(cmd), file=sys.stderr)
        check_call(cmd, cwd=cwd)
