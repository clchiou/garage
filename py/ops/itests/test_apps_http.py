import unittest

from subprocess import Popen

from .fixtures import Fixture


@Fixture.inside_container
class AppsHttpTest(Fixture):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.httpd_proc = Popen(
            ['python3', '-m', 'http.server', '8080'],
            cwd=str(cls.testdata_path),
        )

    @classmethod
    def tearDownClass(cls):
        cls.httpd_proc.terminate()
        cls.httpd_proc.wait()
        super().tearDownClass()

    # NOTE: Use test name format "test_XXXX_..." to ensure test order.
    # (We need this because integration tests are stateful.)

    def test_0000_no_pods(self):
        self.assertEqual([], self.list_pods())

    def test_0001_deploy_pod(self):
        dir_paths = [
            '/etc/ops/apps/pods/test-http-pod/1001',
            '/var/lib/ops/apps/volumes/test-http-pod/1001/volume-1',
        ]
        services = [
            '/etc/systemd/system/test-http-pod-volume-1001.service',
        ]

        for service in services:
            self.assertNotFile(service)
            self.assertNotDir('%s.d' % service)
        for dir_path in dir_paths:
            self.assertNotDir(dir_path)

        self.deploy(self.testdata_path / 'bundle4')

        for service in services:
            self.assertFile(service)
            self.assertFile('%s.d/10-pod-manifest.conf' % service)
        for dir_path in dir_paths:
            self.assertDir(dir_path)

        self.assertEqualContents(
            self.testdata_path / 'bundle3/volume.service',
            '/etc/systemd/system/test-http-pod-volume-1001.service',
        )

    def test_0002_undeploy_pod(self):
        self.undeploy(self.testdata_path / 'bundle4', remove=True)
        self.assertEqual([], self.list_pods())


if __name__ == '__main__':
    unittest.main()
