import unittest

from ops import repos


class ReposTest(unittest.TestCase):

    def test_ports(self):
        ports = repos.Ports([])
        self.assertEqual([], list(ports))
        self.assertEqual(-1, ports._last_port)
        self.assertEqual(30000, ports.next_available_port())

        ports = repos.Ports([
            ('pod-1', 1001, {
                'ports': [
                    {'name': 'http', 'hostPort': 8000},
                    {'name': 'tcp', 'hostPort': 30000},
                ],
            }),
            ('pod-1', 1002, {
                'ports': [
                    {'name': 'http', 'hostPort': 8000},
                    {'name': 'tcp', 'hostPort': 32766},
                ],
            }),
        ])
        self.assertEqual(
            [
                ('pod-1', 1001, 'http', 8000),
                ('pod-1', 1002, 'http', 8000),
                ('pod-1', 1001, 'tcp', 30000),
                ('pod-1', 1002, 'tcp', 32766),
            ],
            list(ports),
        )
        self.assertEqual(32766, ports._last_port)

        # next_available_port is not stateful - may called repeatedly.
        self.assertEqual(32767, ports.next_available_port())
        self.assertEqual(32767, ports.next_available_port())

        ports.register(ports.Port(
            pod_name='pod-1',
            pod_version=1003,
            name='scp',
            port=32767,
        ))
        self.assertEqual(
            [
                ('pod-1', 1001, 'http', 8000),
                ('pod-1', 1002, 'http', 8000),
                ('pod-1', 1001, 'tcp', 30000),
                ('pod-1', 1002, 'tcp', 32766),
                ('pod-1', 1003, 'scp', 32767),
            ],
            list(ports),
        )
        self.assertEqual(32767, ports._last_port)
        self.assertEqual(30001, ports.next_available_port())

        with self.assertRaisesRegex(ValueError, 'port has been allocated'):
            ports.register(ports.Port(
                pod_name='pod-2',
                pod_version=1007,
                name='zyx',
                port=32767,
            ))

        with self.assertRaisesRegex(ValueError, 'duplicated port'):
            repos.Ports([
                ('p1', 1, {'ports': [{'name': 'tcp', 'hostPort': 30011}]}),
                ('p2', 3, {'ports': [{'name': 'tcp', 'hostPort': 30011}]}),
            ])


if __name__ == '__main__':
    unittest.main()
