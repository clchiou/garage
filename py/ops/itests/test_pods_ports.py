import unittest

from subprocess import Popen

from .fixtures import Fixture


@Fixture.inside_container
class PodsPortsTest(Fixture):

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
        self.assertEqual([], self.list_ports())

    def test_0001_deploy_v1001(self):
        self.deploy(self.testdata_path / 'test_pods_ports/1001.json')
        self.assertEqual(['test-ports-pod:1001'], self.list_pods())
        self.assertEqual(
            [
                'test-ports-pod:1001 http 8000',
                'test-ports-pod:1001 https 8443',
                'test-ports-pod:1001 service1 30000',
                'test-ports-pod:1001 service2 30001',
            ],
            self.list_ports(),
        )

    def test_0002_stop_v1001(self):
        self.stop('test-ports-pod:1001')
        self.assertEqual(['test-ports-pod:1001'], self.list_pods())
        self.assertEqual(
            [
                'test-ports-pod:1001 http 8000',
                'test-ports-pod:1001 https 8443',
                'test-ports-pod:1001 service1 30000',
                'test-ports-pod:1001 service2 30001',
            ],
            self.list_ports(),
        )

    def test_0003_restart_v1001(self):
        self.start('test-ports-pod:1001')
        self.assertEqual(['test-ports-pod:1001'], self.list_pods())
        self.assertEqual(
            [
                'test-ports-pod:1001 http 8000',
                'test-ports-pod:1001 https 8443',
                'test-ports-pod:1001 service1 30000',
                'test-ports-pod:1001 service2 30001',
            ],
            self.list_ports(),
        )

    def test_0004_deploy_v1002(self):
        self.deploy(self.testdata_path / 'test_pods_ports/1002.json')
        self.assertEqual(
            [
                'test-ports-pod:1001',
                'test-ports-pod:1002',
            ],
            self.list_pods(),
        )
        self.assertEqual(
            [
                'test-ports-pod:1001 http 8000',
                'test-ports-pod:1001 https 8443',
                'test-ports-pod:1002 http 8000',
                'test-ports-pod:1002 https 8443',
                'test-ports-pod:1001 service1 30000',
                'test-ports-pod:1001 service2 30001',
                'test-ports-pod:1002 service1 30002',
                'test-ports-pod:1002 service2 30003',
            ],
            self.list_ports(),
        )

    def test_0005_undeploy_v1001(self):
        self.stop('test-ports-pod:1001')
        self.undeploy('test-ports-pod:1001')
        self.assertEqual(['test-ports-pod:1002'], self.list_pods())
        self.assertEqual(
            [
                'test-ports-pod:1002 http 8000',
                'test-ports-pod:1002 https 8443',
                'test-ports-pod:1002 service1 30002',
                'test-ports-pod:1002 service2 30003',
            ],
            self.list_ports(),
        )

    def test_0006_redeploy_v1001(self):
        self.deploy(self.testdata_path / 'test_pods_ports/1001.json')
        self.assertEqual(
            [
                'test-ports-pod:1001',
                'test-ports-pod:1002',
            ],
            self.list_pods(),
        )
        self.assertEqual(
            [
                'test-ports-pod:1001 http 8000',
                'test-ports-pod:1001 https 8443',
                'test-ports-pod:1002 http 8000',
                'test-ports-pod:1002 https 8443',
                'test-ports-pod:1002 service1 30002',
                'test-ports-pod:1002 service2 30003',
                'test-ports-pod:1001 service1 30004',
                'test-ports-pod:1001 service2 30005',
            ],
            self.list_ports(),
        )

    def test_0007_undeploy_all(self):
        self.stop('test-ports-pod:1001')
        self.undeploy('test-ports-pod:1001')
        self.stop('test-ports-pod:1002')
        self.undeploy('test-ports-pod:1002')
        self.assertEqual([], self.list_pods())
        self.assertEqual([], self.list_ports())


if __name__ == '__main__':
    unittest.main()
