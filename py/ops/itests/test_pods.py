import unittest

from .fixtures import Fixture


@Fixture.inside_container
class PodsTest(Fixture, unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()

    # NOTE: Use test name format "test_XXXX_..." to ensure test order.
    # (We need this because integration tests are stateful.)

    def test_0000_no_pods(self):
        self.assertEqual([], self.list_pods())
        self.assertFalse(self.is_deployed('test-pod:1001'))
        self.assertFalse(self.is_deployed('test-pod:1002'))
        self.assertFalse(self.is_deployed('test-pod:1003'))

    def test_0100_deploy_empty_bundle(self):
        self.assert_1001_undeployed()

        self.deploy(self.testdata_path / 'bundle1')
        self.assert_1001_deployed()

        # Re-deploy the current pod is a no-op.
        self.deploy(self.testdata_path / 'bundle1')
        self.deploy(self.testdata_path / 'bundle1')
        self.assert_1001_deployed()

        self.start('test-pod:1001')
        self.assert_1001_started()

        self.assertEqual(
            ['test-pod:1001'],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('test-pod:1001'))
        self.assertFalse(self.is_deployed('test-pod:1002'))
        self.assertFalse(self.is_deployed('test-pod:1003'))

    def test_0200_deploy_replicated_bundle(self):
        self.assert_1002_undeployed()

        self.deploy(self.testdata_path / 'bundle2')
        self.assert_1002_deployed()

        self.start('test-pod:1002')
        self.assert_1002_started()

        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002'],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('test-pod:1001'))
        self.assertTrue(self.is_deployed('test-pod:1002'))
        self.assertFalse(self.is_deployed('test-pod:1003'))

    def test_0300_deploy_bundle_with_images_and_volumes(self):
        self.assert_1003_undeployed()

        self.deploy(self.testdata_path / 'bundle3')
        self.assert_1003_deployed()

        self.start('test-pod:1003')
        self.assert_1003_started()

        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002', 'test-pod:1003'],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('test-pod:1001'))
        self.assertTrue(self.is_deployed('test-pod:1002'))
        self.assertTrue(self.is_deployed('test-pod:1003'))

    def test_0400_stop_v1002(self):
        self.assert_1002_started()

        self.stop('test-pod:1002')
        self.assert_1002_deployed()

        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002', 'test-pod:1003'],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('test-pod:1001'))
        self.assertTrue(self.is_deployed('test-pod:1002'))
        self.assertTrue(self.is_deployed('test-pod:1003'))

    def test_0500_stop_v1001(self):
        self.assert_1001_started()

        self.stop('test-pod:1001')
        self.assert_1001_deployed()

        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002', 'test-pod:1003'],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('test-pod:1001'))
        self.assertTrue(self.is_deployed('test-pod:1002'))
        self.assertTrue(self.is_deployed('test-pod:1003'))

    def test_0600_stop_v1003(self):
        self.assert_1003_started()

        self.stop('test-pod:1003')
        self.assert_1003_deployed()

        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002', 'test-pod:1003'],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('test-pod:1001'))
        self.assertTrue(self.is_deployed('test-pod:1002'))
        self.assertTrue(self.is_deployed('test-pod:1003'))

    def test_0700_start_v1003_again(self):
        self.assert_1003_deployed()

        self.start('test-pod:1003')
        self.assert_1003_started()

        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002', 'test-pod:1003'],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('test-pod:1001'))
        self.assertTrue(self.is_deployed('test-pod:1002'))
        self.assertTrue(self.is_deployed('test-pod:1003'))

    def test_0800_undeploy_v1003(self):
        self.assert_1003_started()

        self.undeploy('test-pod:1003')
        self.assert_1003_undeployed()

        # Undeploy the same pod is okay.
        self.undeploy('test-pod:1003')
        self.undeploy('test-pod:1003')
        self.assert_1003_undeployed()

        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002'],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('test-pod:1001'))
        self.assertTrue(self.is_deployed('test-pod:1002'))
        self.assertFalse(self.is_deployed('test-pod:1003'))

    def test_0900_undeploy_all(self):
        self.undeploy('test-pod:1001')
        self.undeploy('test-pod:1002')
        self.assert_1001_undeployed()
        self.assert_1002_undeployed()
        self.assert_1003_undeployed()
        self.assertEqual([], self.list_pods())
        self.assertFalse(self.is_deployed('test-pod:1001'))
        self.assertFalse(self.is_deployed('test-pod:1002'))
        self.assertFalse(self.is_deployed('test-pod:1003'))

    # Assertions on pod states.

    POD_1001_SERVICES = [
        '/etc/systemd/system/test-pod-simple-1001.service',
        '/etc/systemd/system/test-pod-complex-1001.service',
    ]

    def _assert_1001_deployed(self):
        self.assertFile('/var/lib/ops/v1/pods/test-pod/1001/pod.json')
        self.assertFile('/var/lib/ops/v1/pods/test-pod/1001/pod-manifest.json')
        self.assertNotDir('/var/lib/ops/v1/pods/test-pod/1001/volumes')

    def _assert_1001_stopped(self):
        for service in self.POD_1001_SERVICES:
            self.assertNotFile(service)
            self.assertNotDir('%s.d' % service)

    def assert_1001_deployed(self):
        self._assert_1001_deployed()
        self._assert_1001_stopped()

    def assert_1001_started(self):
        self._assert_1001_deployed()
        for service in self.POD_1001_SERVICES:
            self.assertFile(service)
            self.assertFile('%s.d/10-pod-manifest.conf' % service)

    def assert_1001_undeployed(self):
        self.assertNotDir('/var/lib/ops/v1/pods/test-pod/1001')
        self._assert_1001_stopped()

    POD_1002_SERVICES = [
        '/etc/systemd/system/test-pod-replicated-1002@.service',
    ]

    def _assert_1002_deployed(self):
        self.assertFile('/var/lib/ops/v1/pods/test-pod/1002/pod.json')
        self.assertFile('/var/lib/ops/v1/pods/test-pod/1002/pod-manifest.json')
        self.assertNotDir('/var/lib/ops/v1/pods/test-pod/1002/volumes')

    def _assert_1002_stopped(self):
        for service in self.POD_1002_SERVICES:
            self.assertNotFile(service)
            self.assertNotDir('%s.d' % service)

    def assert_1002_deployed(self):
        self._assert_1002_deployed()
        self._assert_1002_stopped()

    def assert_1002_started(self):
        self._assert_1002_deployed()
        # Can't fully test templated services in a Docker container.
        for service in self.POD_1002_SERVICES:
            self.assertFile(service)
            self.assertFile('%s.d/10-pod-manifest.conf' % service)

    def assert_1002_undeployed(self):
        self.assertNotDir('/var/lib/ops/v1/pods/test-pod/1002')
        self._assert_1002_stopped()

    POD_1003_SERVICES = [
        '/etc/systemd/system/test-pod-volume-1003.service',
    ]

    # This SHA should match pod.json, which in turn, matches image.aci.
    BUNDLE3_SHA512 = 'sha512-f369d16070'

    def _assert_1003_deployed(self):
        self.assertFile('/var/lib/ops/v1/pods/test-pod/1003/pod.json')
        self.assertFile('/var/lib/ops/v1/pods/test-pod/1003/pod-manifest.json')
        # These volumes should match pod.json.
        self.assertDir('/var/lib/ops/v1/pods/test-pod/1003/volumes/volume-1')
        self.assertDir('/var/lib/ops/v1/pods/test-pod/1003/volumes/volume-2')
        self.assertImage(self.BUNDLE3_SHA512)

    def _assert_1003_stopped(self):
        for service in self.POD_1003_SERVICES:
            self.assertNotFile(service)
            self.assertNotDir('%s.d' % service)

    def assert_1003_deployed(self):
        self._assert_1003_deployed()
        self._assert_1003_stopped()

    def assert_1003_started(self):
        self._assert_1003_deployed()
        for service in self.POD_1003_SERVICES:
            self.assertFile(service)
            self.assertFile('%s.d/10-pod-manifest.conf' % service)

    def assert_1003_undeployed(self):
        self.assertNotDir('/var/lib/ops/v1/pods/test-pod/1003')
        self.assertNotImage(self.BUNDLE3_SHA512)
        self._assert_1003_stopped()


if __name__ == '__main__':
    unittest.main()
