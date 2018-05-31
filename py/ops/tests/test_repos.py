import unittest

from ops.onboard import repos


class ReposTest(unittest.TestCase):

    def test_ports_empty(self):
        ports = repos.Ports([])
        self.assertEqual([], list(ports))
        self.assertEqual(-1, ports._last_port)
        self.assertEqual(30000, ports.next_available_port())

    def test_ports(self):
        ports = repos.Ports([
            ('pod-1', 1001, None, {
                'ports': [
                    {'name': 'http', 'hostPort': 8000},
                    {'name': 'tcp', 'hostPort': 30000},
                ],
            }),
            ('pod-1', 1002, None, {
                'ports': [
                    {'name': 'http', 'hostPort': 8001},
                    {'name': 'tcp', 'hostPort': 32766},
                ],
            }),
        ])
        self.assertEqual(
            [
                ('pod-1', 1001, None, 'http', 8000),
                ('pod-1', 1001, None, 'tcp', 30000),
                ('pod-1', 1002, None, 'http', 8001),
                ('pod-1', 1002, None, 'tcp', 32766),
            ],
            list(ports),
        )
        self.assertEqual(32766, ports._last_port)

        self.assertTrue(ports.is_allocated(30000))
        self.assertTrue(ports.is_allocated(32766))
        self.assertFalse(ports.is_allocated(32767))

        # next_available_port is not stateful - may called repeatedly.
        self.assertEqual(32767, ports.next_available_port())
        self.assertEqual(32767, ports.next_available_port())

        ports.allocate(ports.Port(
            pod_name='pod-1',
            pod_version=1003,
            instance=None,
            name='scp',
            port=32767,
        ))
        self.assertEqual(
            [
                ('pod-1', 1001, None, 'http', 8000),
                ('pod-1', 1001, None, 'tcp', 30000),
                ('pod-1', 1002, None, 'http', 8001),
                ('pod-1', 1002, None, 'tcp', 32766),
                ('pod-1', 1003, None, 'scp', 32767),
            ],
            list(ports),
        )
        self.assertTrue(ports.is_allocated(32767))
        self.assertEqual(32767, ports._last_port)
        self.assertEqual(30001, ports.next_available_port())

        with self.assertRaisesRegex(ValueError, 'port has been allocated'):
            ports.allocate(ports.Port(
                pod_name='pod-2',
                pod_version=1007,
                instance=None,
                name='zyx',
                port=32767,
            ))

    def test_ports_duplicates(self):
        with self.assertRaisesRegex(ValueError, 'duplicated port'):
            repos.Ports([
                ('p1', 1, None, {'ports': [{'name': 'tcp', 'hostPort': 30011}]}),
                ('p2', 3, None, {'ports': [{'name': 'tcp', 'hostPort': 30011}]}),
            ])


if __name__ == '__main__':
    unittest.main()
