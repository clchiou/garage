import unittest

from .fixtures import Fixture


@Fixture.inside_container
class PodsTest(Fixture, unittest.TestCase):

    # NOTE: Use test name format "test_XXXX_..." to ensure test order.
    # (We need this because integration tests are stateful.)

    def test_0000_no_pods(self):
        self.assertEqual([], self.list_pods())
        self.assertFalse(self.is_deployed('//foo/bar:test-pod@1001'))
        self.assertFalse(self.is_deployed('//foo/bar:test-pod@1002'))
        self.assertFalse(self.is_deployed('//foo/bar:test-pod@1003'))

    def test_0100_deploy_empty_bundle(self):
        self.assert_1001_undeployed()

        self.deploy(self.testdata_path / 'bundle1')
        self.assert_1001_deployed()

        # Re-deploy the current pod is a no-op.
        self.deploy(self.testdata_path / 'bundle1')
        self.deploy(self.testdata_path / 'bundle1')
        self.assert_1001_deployed()

        self.enable('//foo/bar:test-pod@1001')
        self.assert_enabled('1001')

        self.start('//foo/bar:test-pod@1001')
        self.assert_started('1001')

        # Re-start should be a no-ops.
        self.start('//foo/bar:test-pod@1001')
        self.start('//foo/bar:test-pod@1001')
        self.assert_started('1001')

        self.assertEqual(
            ['//foo/bar:test-pod@1001'],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1001'))
        self.assertFalse(self.is_deployed('//foo/bar:test-pod@1002'))
        self.assertFalse(self.is_deployed('//foo/bar:test-pod@1003'))

    def test_0200_deploy_replicated_bundle(self):
        self.assert_1002_undeployed()

        self.deploy(self.testdata_path / 'bundle2')
        self.assert_1002_deployed()

        self.enable('//foo/bar:test-pod@1002')
        self.assert_enabled('1002')

        self.start('//foo/bar:test-pod@1002')
        self.assert_started('1002')

        self.start('//foo/bar:test-pod@1002', extra_args=['--instance-all'])
        all_units = {
            'foo--bar--test-pod--replicated--1002@x.service',
            'foo--bar--test-pod--replicated--1002@y.service',
            'foo--bar--test-pod--replicated--1002@z.service',
        }
        self.assertTrue(
            all_units.issubset(self.systemd_started),
            str(self.systemd_started),
        )

        self.stop('//foo/bar:test-pod@1002')
        self.assertTrue(
            all_units.isdisjoint(self.systemd_started),
            str(self.systemd_started),
        )

        self.start('//foo/bar:test-pod@1002', extra_args=['--instance', 'z'])
        other_than_z = {
            'foo--bar--test-pod--replicated--1002@x.service',
            'foo--bar--test-pod--replicated--1002@y.service',
        }
        only_z = {
            'foo--bar--test-pod--replicated--1002@z.service',
        }
        self.assertTrue(
            other_than_z.isdisjoint(self.systemd_started),
            str(self.systemd_started),
        )
        self.assertTrue(
            only_z.issubset(self.systemd_started),
            str(self.systemd_started),
        )

        self.stop('//foo/bar:test-pod@1002', extra_args=['--instance', 'z'])
        self.assertTrue(
            all_units.isdisjoint(self.systemd_started),
            str(self.systemd_started),
        )

        self.start('//foo/bar:test-pod@1002')

        self.assertEqual(
            [
                '//foo/bar:test-pod@1001',
                '//foo/bar:test-pod@1002',
            ],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1001'))
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1002'))
        self.assertFalse(self.is_deployed('//foo/bar:test-pod@1003'))

    def test_0300_deploy_bundle_with_images_and_volumes(self):
        self.assert_1003_undeployed()

        self.deploy(self.testdata_path / 'bundle3')
        self.assert_1003_deployed()

        self.enable('//foo/bar:test-pod@1003')
        self.assert_enabled('1003')

        self.start('//foo/bar:test-pod@1003')
        self.assert_started('1003')

        self.assertEqual(
            [
                '//foo/bar:test-pod@1001',
                '//foo/bar:test-pod@1002',
                '//foo/bar:test-pod@1003',
            ],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1001'))
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1002'))
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1003'))

    def test_0400_stop_v1002(self):
        self.assert_started('1002')

        self.stop('//foo/bar:test-pod@1002')
        self.assert_stopped('1002')
        self.assert_1002_deployed()
        self.assert_enabled('1002')

        self.assertEqual(
            [
                '//foo/bar:test-pod@1001',
                '//foo/bar:test-pod@1002',
                '//foo/bar:test-pod@1003',
            ],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1001'))
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1002'))
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1003'))

    def test_0500_stop_v1001(self):
        self.assert_started('1001')

        self.stop('//foo/bar:test-pod@1001')
        self.assert_stopped('1001')
        self.assert_1001_deployed()
        self.assert_enabled('1001')

        self.assertEqual(
            [
                '//foo/bar:test-pod@1001',
                '//foo/bar:test-pod@1002',
                '//foo/bar:test-pod@1003',
            ],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1001'))
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1002'))
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1003'))

    def test_0600_stop_v1003(self):
        self.assert_started('1003')

        self.stop('//foo/bar:test-pod@1003')
        self.assert_stopped('1003')
        self.assert_1003_deployed()
        self.assert_enabled('1003')

        self.assertEqual(
            [
                '//foo/bar:test-pod@1001',
                '//foo/bar:test-pod@1002',
                '//foo/bar:test-pod@1003',
            ],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1001'))
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1002'))
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1003'))

    def test_0700_start_v1003_again(self):
        self.assert_1003_deployed()

        self.start('//foo/bar:test-pod@1003')
        self.assert_started('1003')

        self.assertEqual(
            [
                '//foo/bar:test-pod@1001',
                '//foo/bar:test-pod@1002',
                '//foo/bar:test-pod@1003',
            ],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1001'))
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1002'))
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1003'))

    def test_0800_undeploy_v1003(self):
        self.assert_started('1003')

        self.undeploy('//foo/bar:test-pod@1003')
        self.assert_1003_undeployed()

        # Undeploy the same pod is okay.
        self.undeploy('//foo/bar:test-pod@1003')
        self.undeploy('//foo/bar:test-pod@1003')
        self.assert_1003_undeployed()
        self.assert_stopped('1003')
        self.assert_disabled('1003')

        self.assertEqual(
            [
                '//foo/bar:test-pod@1001',
                '//foo/bar:test-pod@1002',
            ],
            self.list_pods(),
        )
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1001'))
        self.assertTrue(self.is_deployed('//foo/bar:test-pod@1002'))
        self.assertFalse(self.is_deployed('//foo/bar:test-pod@1003'))

    def test_0900_undeploy_all(self):
        self.undeploy('//foo/bar:test-pod@1001')
        self.undeploy('//foo/bar:test-pod@1002')

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

        self.assertFalse(self.is_deployed('//foo/bar:test-pod@1001'))
        self.assertFalse(self.is_deployed('//foo/bar:test-pod@1002'))
        self.assertFalse(self.is_deployed('//foo/bar:test-pod@1003'))

    # Assertions on pod states.

    UNIT_FILES = {
        '1001': [
            '/etc/systemd/system/foo--bar--test-pod--simple--1001.service',
            '/etc/systemd/system/foo--bar--test-pod--complex--1001.service',
        ],
        '1002': [
            '/etc/systemd/system/foo--bar--test-pod--replicated--1002@.service',
        ],
        '1003': [
            '/etc/systemd/system/foo--bar--test-pod--volume--1003.service',
        ],
    }

    UNIT_DROPINS = {
        '1001': [
            '/etc/systemd/system/foo--bar--test-pod--simple--1001.service.d',
            '/etc/systemd/system/foo--bar--test-pod--complex--1001.service.d',
        ],
        '1002': [
            '/etc/systemd/system/foo--bar--test-pod--replicated--1002@x.service.d',
            '/etc/systemd/system/foo--bar--test-pod--replicated--1002@y.service.d',
            '/etc/systemd/system/foo--bar--test-pod--replicated--1002@z.service.d',
        ],
        '1003': [
            '/etc/systemd/system/foo--bar--test-pod--volume--1003.service.d',
        ],
    }

    UNIT_DROPIN_CONTENT_REGEXS = {
        '1001': (
            r'Environment="POD_NAME=//foo/bar:test-pod".*'
            r'Environment="POD_VERSION=1001"'
        ),
        '1002': (
            r'Environment="POD_NAME=//foo/bar:test-pod".*'
            r'Environment="POD_VERSION=1002"'
        ),
        '1003': (
            r'Environment="POD_NAME=//foo/bar:test-pod".*'
            r'Environment="POD_VERSION=1003"'
        ),
    }

    UNIT_NAMES = {
        '1001': {
            'enable': {
                'foo--bar--test-pod--simple--1001.service',
                'foo--bar--test-pod--complex--1001.service',
            },
            'enable-not': set(),
            'start': {
                'foo--bar--test-pod--simple--1001.service',
                'foo--bar--test-pod--complex--1001.service',
            },
            'start-not': set(),
        },
        '1002': {
            'enable': {
                'foo--bar--test-pod--replicated--1002@x.service',
                'foo--bar--test-pod--replicated--1002@y.service',
                'foo--bar--test-pod--replicated--1002@z.service',
            },
            'enable-not': set(),
            'start': {
                'foo--bar--test-pod--replicated--1002@x.service',
            },
            'start-not': {
                'foo--bar--test-pod--replicated--1002@y.service',
                'foo--bar--test-pod--replicated--1002@z.service',
            },
        },
        '1003': {
            'enable': {
                'foo--bar--test-pod--volume--1003.service',
            },
            'enable-not': set(),
            'start': {
                'foo--bar--test-pod--volume--1003.service',
            },
            'start-not': set(),
        },
    }

    def assert_unit_installed(self, version):
        for path in self.UNIT_FILES[version]:
            self.assertFile(path)
        for path in self.UNIT_DROPINS[version]:
            self.assertDir(path)
            self.assertFileContentRegex(
                '%s/10-pod-manifest.conf' % path,
                self.UNIT_DROPIN_CONTENT_REGEXS[version],
            )

    def assert_unit_uninstalled(self, version):
        for path in self.UNIT_FILES[version]:
            self.assertNotFile(path)
        for path in self.UNIT_DROPINS[version]:
            self.assertNotDir(path)

    def assert_enabled(self, version):
        data = self.UNIT_NAMES[version]['enable']
        self.assertTrue(
            data.issubset(self.systemd_enabled),
            str(self.systemd_enabled),
        )
        data = self.UNIT_NAMES[version]['enable-not']
        self.assertTrue(
            data.isdisjoint(self.systemd_enabled),
            str(self.systemd_enabled),
        )

    def assert_started(self, version):
        data = self.UNIT_NAMES[version]['start']
        self.assertTrue(
            data.issubset(self.systemd_started),
            str(self.systemd_started),
        )
        data = self.UNIT_NAMES[version]['start-not']
        self.assertTrue(
            data.isdisjoint(self.systemd_started),
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
        self.assertFile('/var/lib/ops/v1/pods/foo--bar--test-pod/1001/pod.json')
        self.assertFile(
            '/var/lib/ops/v1/pods/foo--bar--test-pod/1001/pod-manifest.json')
        self.assertFile(
            '/var/lib/ops/v1/pods/foo--bar--test-pod/1001/pod-manifests/'
            'foo--bar--test-pod--simple--1001.service.json')
        self.assertFile(
            '/var/lib/ops/v1/pods/foo--bar--test-pod/1001/pod-manifests/'
            'foo--bar--test-pod--complex--1001.service.json')
        self.assertNotDir('/var/lib/ops/v1/pods/foo--bar--test-pod/1001/volumes')
        self.assert_unit_installed('1001')

    def assert_1001_undeployed(self):
        self.assertNotDir('/var/lib/ops/v1/pods/foo--bar--test-pod/1001')
        self.assert_unit_uninstalled('1001')

    def assert_1002_deployed(self):
        self.assertFile('/var/lib/ops/v1/pods/foo--bar--test-pod/1002/pod.json')
        self.assertFile(
            '/var/lib/ops/v1/pods/foo--bar--test-pod/1002/pod-manifest.json')
        self.assertFile(
            '/var/lib/ops/v1/pods/foo--bar--test-pod/1002/pod-manifests/'
            'foo--bar--test-pod--replicated--1002@x.service.json')
        self.assertFile(
            '/var/lib/ops/v1/pods/foo--bar--test-pod/1002/pod-manifests/'
            'foo--bar--test-pod--replicated--1002@y.service.json')
        self.assertFile(
            '/var/lib/ops/v1/pods/foo--bar--test-pod/1002/pod-manifests/'
            'foo--bar--test-pod--replicated--1002@z.service.json')
        self.assertNotDir('/var/lib/ops/v1/pods/foo--bar--test-pod/1002/volumes')
        self.assert_unit_installed('1002')

    def assert_1002_undeployed(self):
        self.assertNotDir('/var/lib/ops/v1/pods/foo--bar--test-pod/1002')
        self.assert_unit_uninstalled('1002')

    # This SHA should match pod.json, which in turn, matches image.aci.
    BUNDLE3_SHA512 = 'sha512-f369d16070'

    def assert_1003_deployed(self):
        self.assertFile('/var/lib/ops/v1/pods/foo--bar--test-pod/1003/pod.json')
        self.assertFile(
            '/var/lib/ops/v1/pods/foo--bar--test-pod/1003/pod-manifest.json')
        self.assertFile(
            '/var/lib/ops/v1/pods/foo--bar--test-pod/1003/pod-manifests/'
            'foo--bar--test-pod--volume--1003.service.json')
        # These volumes should match pod.json.
        self.assertDir('/var/lib/ops/v1/pods/foo--bar--test-pod/1003/volumes/volume-1')
        self.assertDir('/var/lib/ops/v1/pods/foo--bar--test-pod/1003/volumes/volume-2')
        self.assertImage(self.BUNDLE3_SHA512)
        self.assert_unit_installed('1003')

    def assert_1003_undeployed(self):
        self.assertNotDir('/var/lib/ops/v1/pods/foo--bar--test-pod/1003')
        self.assertNotImage(self.BUNDLE3_SHA512)
        self.assert_unit_uninstalled('1003')


if __name__ == '__main__':
    unittest.main()
