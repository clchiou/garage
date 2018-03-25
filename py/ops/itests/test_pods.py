import unittest

from .fixtures import Fixture


@Fixture.inside_container
class PodsTest(Fixture, unittest.TestCase):

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

        self.enable('test-pod:1001')
        self.assert_enabled('1001')

        self.start('test-pod:1001')
        self.assert_started('1001')

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

        self.enable('test-pod:1002')
        self.assert_enabled('1002')

        self.start('test-pod:1002')
        self.assert_started('1002')

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

        self.enable('test-pod:1003')
        self.assert_enabled('1003')

        self.start('test-pod:1003')
        self.assert_started('1003')

        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002', 'test-pod:1003'],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('test-pod:1001'))
        self.assertTrue(self.is_deployed('test-pod:1002'))
        self.assertTrue(self.is_deployed('test-pod:1003'))

    def test_0400_stop_v1002(self):
        self.assert_started('1002')

        self.stop('test-pod:1002')
        self.assert_stopped('1002')
        self.assert_1002_deployed()
        self.assert_enabled('1002')

        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002', 'test-pod:1003'],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('test-pod:1001'))
        self.assertTrue(self.is_deployed('test-pod:1002'))
        self.assertTrue(self.is_deployed('test-pod:1003'))

    def test_0500_stop_v1001(self):
        self.assert_started('1001')

        self.stop('test-pod:1001')
        self.assert_stopped('1001')
        self.assert_1001_deployed()
        self.assert_enabled('1001')

        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002', 'test-pod:1003'],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('test-pod:1001'))
        self.assertTrue(self.is_deployed('test-pod:1002'))
        self.assertTrue(self.is_deployed('test-pod:1003'))

    def test_0600_stop_v1003(self):
        self.assert_started('1003')

        self.stop('test-pod:1003')
        self.assert_stopped('1003')
        self.assert_1003_deployed()
        self.assert_enabled('1003')

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
        self.assert_started('1003')

        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002', 'test-pod:1003'],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('test-pod:1001'))
        self.assertTrue(self.is_deployed('test-pod:1002'))
        self.assertTrue(self.is_deployed('test-pod:1003'))

    def test_0800_undeploy_v1003(self):
        self.assert_started('1003')

        self.undeploy('test-pod:1003')
        self.assert_1003_undeployed()

        # Undeploy the same pod is okay.
        self.undeploy('test-pod:1003')
        self.undeploy('test-pod:1003')
        self.assert_1003_undeployed()
        self.assert_stopped('1003')
        self.assert_disabled('1003')

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

        self.assert_stopped('1001')
        self.assert_stopped('1002')
        self.assert_stopped('1003')

        self.assert_disabled('1001')
        self.assert_disabled('1002')
        self.assert_disabled('1003')

        self.assertEqual([], self.list_pods())

        self.assertFalse(self.is_deployed('test-pod:1001'))
        self.assertFalse(self.is_deployed('test-pod:1002'))
        self.assertFalse(self.is_deployed('test-pod:1003'))

    # Assertions on pod states.

    UNIT_FILES = {
        '1001': [
            '/etc/systemd/system/test-pod-simple-1001.service',
            '/etc/systemd/system/test-pod-complex-1001.service',
        ],
        '1002': [
            '/etc/systemd/system/test-pod-replicated-1002@.service',
        ],
        '1003': [
            '/etc/systemd/system/test-pod-volume-1003.service',
        ],
    }

    UNIT_NAMES = {
        '1001': {
            'enable': {
                'test-pod-simple-1001.service',
                'test-pod-complex-1001.service',
            },
            'start': {
                'test-pod-simple-1001.service',
                'test-pod-complex-1001.service',
            },
        },
        '1002': {
            'enable': {
                'test-pod-replicated-1002@x.service',
                'test-pod-replicated-1002@y.service',
                'test-pod-replicated-1002@z.service',
            },
            'start': {
                'test-pod-replicated-1002@x.service',
            },
        },
        '1003': {
            'enable': {
                'test-pod-volume-1003.service',
            },
            'start': {
                'test-pod-volume-1003.service',
            },
        },
    }

    def assert_unit_installed(self, version):
        for service in self.UNIT_FILES[version]:
            self.assertFile(service)
            self.assertDir('%s.d' % service)

    def assert_unit_uninstalled(self, version):
        for service in self.UNIT_FILES[version]:
            self.assertNotFile(service)
            self.assertNotDir('%s.d' % service)

    def assert_enabled(self, version):
        data = self.UNIT_NAMES[version]['enable']
        self.assertTrue(
            data.issubset(self.systemd_enabled),
            str(self.systemd_enabled),
        )

    def assert_started(self, version):
        data = self.UNIT_NAMES[version]['start']
        self.assertTrue(
            data.issubset(self.systemd_started),
            str(self.systemd_started),
        )

    def assert_stopped(self, version):
        data = self.UNIT_NAMES[version]['start']
        self.assertTrue(
            data.isdisjoint(self.systemd_started),
            str(self.systemd_started),
        )

    def assert_disabled(self, version):
        data = self.UNIT_NAMES[version]['enable']
        self.assertTrue(
            data.isdisjoint(self.systemd_enabled),
            str(self.systemd_enabled),
        )

    def assert_1001_deployed(self):
        self.assertFile('/var/lib/ops/v1/pods/test-pod/1001/pod.json')
        self.assertFile('/var/lib/ops/v1/pods/test-pod/1001/pod-manifest.json')
        self.assertNotDir('/var/lib/ops/v1/pods/test-pod/1001/volumes')
        self.assert_unit_installed('1001')

    def assert_1001_undeployed(self):
        self.assertNotDir('/var/lib/ops/v1/pods/test-pod/1001')
        self.assert_unit_uninstalled('1001')

    def assert_1002_deployed(self):
        self.assertFile('/var/lib/ops/v1/pods/test-pod/1002/pod.json')
        self.assertFile('/var/lib/ops/v1/pods/test-pod/1002/pod-manifest.json')
        self.assertNotDir('/var/lib/ops/v1/pods/test-pod/1002/volumes')
        self.assert_unit_installed('1002')

    def assert_1002_undeployed(self):
        self.assertNotDir('/var/lib/ops/v1/pods/test-pod/1002')
        self.assert_unit_uninstalled('1002')

    # This SHA should match pod.json, which in turn, matches image.aci.
    BUNDLE3_SHA512 = 'sha512-f369d16070'

    def assert_1003_deployed(self):
        self.assertFile('/var/lib/ops/v1/pods/test-pod/1003/pod.json')
        self.assertFile('/var/lib/ops/v1/pods/test-pod/1003/pod-manifest.json')
        # These volumes should match pod.json.
        self.assertDir('/var/lib/ops/v1/pods/test-pod/1003/volumes/volume-1')
        self.assertDir('/var/lib/ops/v1/pods/test-pod/1003/volumes/volume-2')
        self.assertImage(self.BUNDLE3_SHA512)
        self.assert_unit_installed('1003')

    def assert_1003_undeployed(self):
        self.assertNotDir('/var/lib/ops/v1/pods/test-pod/1003')
        self.assertNotImage(self.BUNDLE3_SHA512)
        self.assert_unit_uninstalled('1003')


if __name__ == '__main__':
    unittest.main()
