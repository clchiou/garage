import unittest

from .fixtures import Fixture


@Fixture.inside_container
class AppsTest(Fixture):

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
        self.assertEqual('undeployed', self.get_pod_state('test-pod:1001'))
        self.assertEqual('undeployed', self.get_pod_state('test-pod:1002'))
        self.assertEqual('undeployed', self.get_pod_state('test-pod:1003'))

    def test_0100_deploy_empty_bundle(self):
        self.assertNoPod1001()
        self.deploy(self.testdata_path / 'bundle1')
        # Re-deploy the current pod is a no-op.
        self.deploy(self.testdata_path / 'bundle1')
        self.deploy(self.testdata_path / 'bundle1')
        self.assertPod1001()
        self.assertEqual(
            ['test-pod:1001 *'],
            self.list_pods(),
        )
        self.assertEqual('current', self.get_pod_state('test-pod:1001'))
        self.assertEqual('undeployed', self.get_pod_state('test-pod:1002'))
        self.assertEqual('undeployed', self.get_pod_state('test-pod:1003'))

        self.annotate_pod('test-pod:1001', 'key-1', 'value-1')
        self.assertEqual(
            'value-1',
            self.get_pod_annotation('test-pod:1001', 'key-1'),
        )

    def test_0200_deploy_replicated_bundle(self):
        self.assertNoPod1002()
        self.deploy(self.testdata_path / 'bundle2')
        self.assertPod1002()
        self.assertNoPod1001Etc()
        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002 *'],
            self.list_pods(),
        )
        self.assertEqual('deployed', self.get_pod_state('test-pod:1001'))
        self.assertEqual('current', self.get_pod_state('test-pod:1002'))
        self.assertEqual('undeployed', self.get_pod_state('test-pod:1003'))

        self.assertEqual(
            'value-1',
            self.get_pod_annotation('test-pod:1001', 'key-1'),
        )

    def test_0300_deploy_bundle_with_images_and_volumes(self):
        self.assertNoPod1003()
        self.deploy(self.testdata_path / 'bundle3')
        self.assertPod1003()
        self.assertNoPod1001Etc()
        self.assertNoPod1002Etc()
        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002', 'test-pod:1003 *'],
            self.list_pods(),
        )
        self.assertEqual('deployed', self.get_pod_state('test-pod:1001'))
        self.assertEqual('deployed', self.get_pod_state('test-pod:1002'))
        self.assertEqual('current', self.get_pod_state('test-pod:1003'))

    def test_0400_redeploy_v1002(self):
        self.assertNoPod1002Etc()
        self.deploy('test-pod:1002')
        self.assertPod1002()
        self.assertNoPod1001Etc()
        self.assertNoPod1003Etc()
        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002 *', 'test-pod:1003'],
            self.list_pods(),
        )
        self.assertEqual('deployed', self.get_pod_state('test-pod:1001'))
        self.assertEqual('current', self.get_pod_state('test-pod:1002'))
        self.assertEqual('deployed', self.get_pod_state('test-pod:1003'))

    def test_0500_redeploy_v1001(self):
        self.assertNoPod1001Etc()
        self.deploy('test-pod:1001')
        self.assertNoPod1002Etc()
        self.assertNoPod1003Etc()
        self.assertEqual(
            ['test-pod:1001 *', 'test-pod:1002', 'test-pod:1003'],
            self.list_pods(),
        )
        self.assertEqual('current', self.get_pod_state('test-pod:1001'))
        self.assertEqual('deployed', self.get_pod_state('test-pod:1002'))
        self.assertEqual('deployed', self.get_pod_state('test-pod:1003'))

    def test_0600_redeploy_v1003(self):
        self.assertNoPod1002Etc()
        self.assertNoPod1003Etc()
        self.deploy('test-pod:1003')
        self.assertNoPod1001Etc()
        self.assertNoPod1002Etc()
        self.assertPod1003()
        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002', 'test-pod:1003 *'],
            self.list_pods(),
        )
        self.assertEqual('deployed', self.get_pod_state('test-pod:1001'))
        self.assertEqual('deployed', self.get_pod_state('test-pod:1002'))
        self.assertEqual('current', self.get_pod_state('test-pod:1003'))

    def test_0700_redeploy_v1003_again(self):
        self.deploy('test-pod:1003')
        self.assertNoPod1001Etc()
        self.assertNoPod1002Etc()
        self.assertPod1003()
        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002', 'test-pod:1003 *'],
            self.list_pods(),
        )
        self.assertEqual('deployed', self.get_pod_state('test-pod:1001'))
        self.assertEqual('deployed', self.get_pod_state('test-pod:1002'))
        self.assertEqual('current', self.get_pod_state('test-pod:1003'))

    def test_0800_undeploy(self):
        self.assertPod1003()

        self.undeploy('test-pod:1003', remove=False)
        # Undeploy the same pod is okay (if not removed).
        self.undeploy('test-pod:1003', remove=False)
        self.undeploy('test-pod:1003', remove=False)
        self.assertPod1003Configs()
        self.assertNoPod1003Etc()
        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002', 'test-pod:1003'],
            self.list_pods(),
        )
        self.assertEqual('deployed', self.get_pod_state('test-pod:1001'))
        self.assertEqual('deployed', self.get_pod_state('test-pod:1002'))
        self.assertEqual('deployed', self.get_pod_state('test-pod:1003'))

    def test_0801_overwrite_volume2_v1003(self):
        self.assertPod1003Configs()
        self.overwrite_volumes(self.testdata_path / 'bundle3')
        self.assertPod1003Configs()

    def test_0802_undeploy_remove(self):
        self.undeploy('test-pod:1003', remove=True)
        self.assertNoPod1003()
        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002'],
            self.list_pods(),
        )
        self.assertEqual('deployed', self.get_pod_state('test-pod:1001'))
        self.assertEqual('deployed', self.get_pod_state('test-pod:1002'))
        self.assertEqual('undeployed', self.get_pod_state('test-pod:1003'))

    def test_0900_redeploy_v1002(self):
        self.deploy('test-pod:1002')
        self.assertPod1002()
        self.assertEqual(
            ['test-pod:1001', 'test-pod:1002 *'],
            self.list_pods(),
        )
        self.assertEqual('deployed', self.get_pod_state('test-pod:1001'))
        self.assertEqual('current', self.get_pod_state('test-pod:1002'))
        self.assertEqual('undeployed', self.get_pod_state('test-pod:1003'))

    def test_1000_undeploy_all(self):
        self.undeploy('test-pod:1001', remove=True)
        self.undeploy('test-pod:1002', remove=True)
        self.assertNoPod1001()
        self.assertNoPod1002()
        self.assertNoPod1003()
        self.assertEqual([], self.list_pods())
        self.assertEqual('undeployed', self.get_pod_state('test-pod:1001'))
        self.assertEqual('undeployed', self.get_pod_state('test-pod:1002'))
        self.assertEqual('undeployed', self.get_pod_state('test-pod:1003'))

    # Assertions on pod states.

    POD_1001_SERVICES = [
        '/etc/systemd/system/test-pod-simple-1001.service',
        '/etc/systemd/system/test-pod-complex-1001.service',
    ]

    def assertPod1001(self):
        self.assertFile('/etc/ops/apps/pods/test-pod/1001/pod.json')
        self.assertFile('/etc/ops/apps/pods/test-pod/1001/pod-manifest.json')
        self.assertNotDir('/var/lib/ops/apps/volumes/test-pod/1001')
        for service in self.POD_1001_SERVICES:
            self.assertFile(service)
            self.assertFile('%s.d/10-pod-manifest.conf' % service)

    def assertNoPod1001(self):
        self.assertNotDir('/etc/ops/apps/pods/test-pod/1001')
        self.assertNotDir('/var/lib/ops/apps/volumes/test-pod/1001')
        self.assertNoPod1001Etc()

    def assertNoPod1001Etc(self):
        for service in self.POD_1001_SERVICES:
            self.assertNotFile(service)
            self.assertNotDir('%s.d' % service)

    POD_1002_SERVICES = [
        '/etc/systemd/system/test-pod-replicated-1002@.service',
    ]

    def assertPod1002(self):
        self.assertFile('/etc/ops/apps/pods/test-pod/1002/pod.json')
        self.assertFile('/etc/ops/apps/pods/test-pod/1002/pod-manifest.json')
        self.assertNotDir('/var/lib/ops/apps/volumes/test-pod/1002')
        # Can't fully test templated services in a Docker container.
        for service in self.POD_1002_SERVICES:
            self.assertFile(service)
            self.assertFile('%s.d/10-pod-manifest.conf' % service)

    def assertNoPod1002(self):
        self.assertNotDir('/etc/ops/apps/pods/test-pod/1002')
        self.assertNotDir('/var/lib/ops/apps/volumes/test-pod/1002')
        self.assertNoPod1002Etc()

    def assertNoPod1002Etc(self):
        for service in self.POD_1002_SERVICES:
            self.assertNotFile(service)
            self.assertNotDir('%s.d' % service)

    POD_1003_SERVICES = [
        '/etc/systemd/system/test-pod-volume-1003.service',
    ]

    # This SHA should match pod.json, which in turn, matches image.aci.
    BUNDLE3_SHA512 = 'sha512-f369d16070'

    def assertPod1003(self):
        self.assertPod1003Configs()
        for service in self.POD_1003_SERVICES:
            self.assertFile(service)
            self.assertFile('%s.d/10-pod-manifest.conf' % service)

    def assertPod1003Configs(self):
        self.assertFile('/etc/ops/apps/pods/test-pod/1003/pod.json')
        self.assertFile('/etc/ops/apps/pods/test-pod/1003/pod-manifest.json')
        # These volumes should match pod.json.
        self.assertDir('/var/lib/ops/apps/volumes/test-pod/1003/volume-1')
        self.assertDir('/var/lib/ops/apps/volumes/test-pod/1003/volume-2')
        self.assertImage(self.BUNDLE3_SHA512)

    def assertNoPod1003(self):
        self.assertNotDir('/etc/ops/apps/pods/test-pod/1003')
        self.assertNotDir('/var/lib/ops/apps/volumes/test-pod/1003')
        self.assertNotImage(self.BUNDLE3_SHA512)
        self.assertNoPod1003Etc()

    def assertNoPod1003Etc(self):
        for service in self.POD_1003_SERVICES:
            self.assertNotFile(service)
            self.assertNotDir('%s.d' % service)


if __name__ == '__main__':
    unittest.main()
