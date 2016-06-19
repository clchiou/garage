import unittest

import getpass
from pathlib import Path
from subprocess import call, check_call, check_output


class AppsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Make sure we are inside a container.
        assert getpass.getuser() == 'plumber'

        # Ensure paths.
        cls.root_path = Path(__file__).parent.parent
        assert (cls.root_path / 'ops').is_dir()
        cls.testdata_path = Path(__file__).parent / 'testdata'
        assert cls.testdata_path.is_dir()

        # Install the fake systemctl because you can't run systemd in a
        # Docker container (can you?).
        check_call(['sudo', 'cp', '/bin/echo', '/usr/local/bin/systemctl'])

    @classmethod
    def tearDownClass(cls):
        # Uninstall the fake systemctl.
        check_call(['sudo', 'rm', '/usr/local/bin/systemctl'])

    # NOTE: Use test name format "test_XXXX_..." to ensure test order.
    # (We need this because integration tests are stateful.)

    def test_0000_no_pods(self):
        self.assertEqual([], self.list_pods())

    def test_0001_deploy_empty_bundle(self):
        self.assertNoPod1001()
        self.deploy(self.testdata_path / 'bundle1')
        self.assertPod1001()
        self.assertEqual(
            ['test-pod:1001 *'],
            self.list_pods(),
        )

    def test_0002_deploy_replicated_bundle(self):
        self.assertNoPod1002()
        self.deploy(self.testdata_path / 'bundle2')
        self.assertPod1002()
        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002 *'],
            self.list_pods(),
        )

    def test_0003_deploy_bundle_with_images_and_volumes(self):
        self.assertNoPod1003()
        self.deploy(self.testdata_path / 'bundle3')
        self.assertPod1003()
        self.assertNoPod1002Etc()
        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002', 'test-pod:1003 *'],
            self.list_pods(),
        )

    def test_0004_redeploy_v1002(self):
        self.assertNoPod1002Etc()
        self.deploy('test-pod:1002', redeploy=True)
        self.assertPod1002()
        self.assertNoPod1003Etc()
        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002 *', 'test-pod:1003'],
            self.list_pods(),
        )

    def test_0005_redeploy_v1001(self):
        self.deploy('test-pod:1001', redeploy=True)
        self.assertNoPod1002Etc()
        self.assertNoPod1003Etc()
        self.assertEqual(
            ['test-pod:1001 *', 'test-pod:1002', 'test-pod:1003'],
            self.list_pods(),
        )

    def test_0006_redeploy_v1003(self):
        self.assertNoPod1002Etc()
        self.assertNoPod1003Etc()
        self.deploy('test-pod:1003', redeploy=True)
        self.assertNoPod1002Etc()
        self.assertPod1003()
        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002', 'test-pod:1003 *'],
            self.list_pods(),
        )

    def test_0007_redeploy_v1003_again(self):
        self.deploy('test-pod:1003', redeploy=True)
        self.assertNoPod1002Etc()
        self.assertPod1003()
        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002', 'test-pod:1003 *'],
            self.list_pods(),
        )

    def test_0008_undeploy(self):
        self.assertPod1003()

        self.undeploy('test-pod:1003', remove=False)
        self.assertPod1003Configs()
        self.assertNoPod1003Etc()
        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002', 'test-pod:1003'],
            self.list_pods(),
        )

        self.undeploy('test-pod:1003', remove=True)
        self.assertNoPod1003()
        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002'],
            self.list_pods(),
        )

    def test_0009_redeploy_v1002(self):
        self.deploy('test-pod:1002', redeploy=True)
        self.assertPod1002()
        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002 *'],
            self.list_pods(),
        )

    def test_0010_undeploy_all(self):
        self.undeploy('test-pod:1001', remove=True)
        self.undeploy('test-pod:1002', remove=True)
        self.assertNoPod1001()
        self.assertNoPod1002()
        self.assertNoPod1003()
        self.assertEqual([], self.list_pods())

    # Assertions on pod states.

    def assertPod1001(self):
        self.assertDir('/etc/ops/apps/pods/test-pod/1001')
        self.assertNotDir('/var/lib/ops/apps/volumes/test-pod/1001')
        # Sanity check.
        self.assertNotFile('/etc/systemd/system/test-pod-example:1001.service')

    def assertNoPod1001(self):
        self.assertNotDir('/etc/ops/apps/pods/test-pod/1001')
        self.assertNotDir('/var/lib/ops/apps/volumes/test-pod/1001')

    def assertPod1002(self):
        self.assertDir('/etc/ops/apps/pods/test-pod/1002')
        self.assertNotDir('/var/lib/ops/apps/volumes/test-pod/1002')
        # Can't fully test templated services in a Docker container.
        services = [
            'test-pod-simple:1002.service',
            'test-pod-replicated:1002@.service',
            'test-pod-replicated-with-arg:1002@.service',
        ]
        for service in services:
            self.assertFile('/etc/systemd/system/%s' % service)
            self.assertNotDir('/etc/systemd/system/%s.d' % service)

    def assertNoPod1002(self):
        self.assertNotDir('/etc/ops/apps/pods/test-pod/1002')
        self.assertNotDir('/var/lib/ops/apps/volumes/test-pod/1002')
        self.assertNoPod1002Etc()

    def assertNoPod1002Etc(self):
        services = [
            'test-pod-simple:1002.service',
            'test-pod-replicated:1002@.service',
            'test-pod-replicated-with-arg:1002@.service',
        ]
        for service in services:
            self.assertNotFile('/etc/systemd/system/%s' % service)
            self.assertNotDir('/etc/systemd/system/%s.d' % service)

    # This SHA should match pod.json, which in turn, matches image.aci.
    bundle3_sha512 = 'sha512-f369d16070'

    def assertPod1003(self):
        self.assertPod1003Configs()
        services = [
            'test-pod-volume:1003.service',
        ]
        for service in services:
            self.assertFile('/etc/systemd/system/%s' % service)
            self.assertFile(
                '/etc/systemd/system/%s.d/10-volumes.conf' % service)

    def assertPod1003Configs(self):
        self.assertDir('/etc/ops/apps/pods/test-pod/1003')
        # These volumes should match pod.json.
        self.assertDir('/var/lib/ops/apps/volumes/test-pod/1003/volume-1')
        self.assertDir('/var/lib/ops/apps/volumes/test-pod/1003/volume-2')
        self.assertImage(self.bundle3_sha512)

    def assertNoPod1003(self):
        self.assertNotDir('/etc/ops/apps/pods/test-pod/1003')
        self.assertNotDir('/var/lib/ops/apps/volumes/test-pod/1003')
        self.assertNotImage(self.bundle3_sha512)
        self.assertNoPod1003Etc()

    def assertNoPod1003Etc(self):
        services = [
            'test-pod-volume:1003.service',
        ]
        for service in services:
            self.assertNotFile('/etc/systemd/system/%s' % service)
            self.assertNotDir('/etc/systemd/system/%s.d' % service)

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

    # ops.apps commands and other helpers.

    def list_pods(self):
        output = check_output(
            ['python3', '-m', 'ops.apps', 'list-pods', '-v'],
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

    def deploy(self, target, *, redeploy=False):
        cmd = ['python3', '-m', 'ops.apps', 'deploy', '-v', str(target)]
        if redeploy:
            cmd.append('--redeploy')
        check_call(cmd, cwd=str(self.root_path))

    def undeploy(self, target, *, remove):
        cmd = ['python3', '-m', 'ops.apps', 'undeploy', '-v', str(target)]
        if remove:
            cmd.append('--remove')
        check_call(cmd, cwd=str(self.root_path))


if __name__ == '__main__':
    unittest.main()
