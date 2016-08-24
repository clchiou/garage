import unittest

from pathlib import Path

from ops.apps import models


class ModelsTest(unittest.TestCase):

    def test_pod(self):
        with self.assertRaisesRegex(KeyError, 'name'):
            models.Pod(Path(__file__), {})
        with self.assertRaisesRegex(KeyError, 'version'):
            models.Pod(Path(__file__), {'name': 'example'})
        with self.assertRaisesRegex(ValueError, 'invalid pod name: x--y'):
            models.Pod(Path(__file__), {'name': 'x--y', 'version': 1001})
        with self.assertRaisesRegex(ValueError, 'invalid literal for int'):
            models.Pod(Path(__file__), {'name': 'x-y', 'version': 'z'})
        with self.assertRaisesRegex(ValueError, 'unknown names: x'):
            models.Pod(Path(__file__), {'name': 'x-y', 'version': 1, 'x': 1})

        pod = models.Pod(Path(__file__), dict(
            name='xy',
            version=1001,
            manifest={},
        ))
        self.assertEqual('xy:1001', str(pod))
        self.assertObjectFields(
            dict(
                path=Path(__file__).absolute(),
                name='xy',
                version=1001,
                systemd_units=(),
                images=(),
                volumes=(),
                manifest={},
            ),
            pod,
        )

    def test_systemd_unit(self):
        pod = models.Pod(Path(__file__), {
            'name': 'xy',
            'version': 1001,
            'systemd-units': [
                {
                    'unit-file': 'example.service',
                },
                {
                    'unit-file': 'sample.timer',
                    'start': True,
                },
                {
                    'unit-file': 'example.service',
                    'instances': 1,
                },
                {
                    'unit-file': 'example.service',
                    'instances': 3,
                },
                {
                    'unit-file': 'example.service',
                    'instances': [8000],
                },
                {
                    'unit-file': 'example.service',
                    'instances': ['a', 'b', 'c'],
                },
            ],
            'manifest': {},
        })
        self.assertEqual(6, len(pod.systemd_units))
        self.assertObjectFields(
            dict(
                path=Path(__file__).parent / 'example.service',
                name='xy-example-1001.service',
                start=False,
                instances=(),
                unit_path=Path('/etc/systemd/system/xy-example-1001.service'),
                dropin_path=Path(
                    '/etc/systemd/system/xy-example-1001.service.d'),
            ),
            pod.systemd_units[0],
        )
        self.assertObjectFields(
            dict(
                path=Path(__file__).parent / 'sample.timer',
                name='xy-sample-1001.timer',
                start=True,
                instances=(),
            ),
            pod.systemd_units[1],
        )
        self.assertObjectFields(
            dict(
                name='xy-example-1001@.service',
                instances=(
                    'xy-example-1001@0.service',
                ),
            ),
            pod.systemd_units[2],
        )
        self.assertObjectFields(
            dict(
                name='xy-example-1001@.service',
                instances=(
                    'xy-example-1001@0.service',
                    'xy-example-1001@1.service',
                    'xy-example-1001@2.service',
                ),
            ),
            pod.systemd_units[3],
        )
        self.assertObjectFields(
            dict(
                name='xy-example-1001@.service',
                instances=(
                    'xy-example-1001@8000.service',
                ),
            ),
            pod.systemd_units[4],
        )
        self.assertObjectFields(
            dict(
                name='xy-example-1001@.service',
                instances=(
                    'xy-example-1001@a.service',
                    'xy-example-1001@b.service',
                    'xy-example-1001@c.service',
                ),
            ),
            pod.systemd_units[5],
        )

    def test_image(self):
        pod = models.Pod(Path(__file__), dict(
            name='xy',
            version=1001,
            images=[
                {'id': 'sha512-XXX', 'uri': 'http://localhost/image.aci'},
                {'id': 'sha512-XXX', 'uri': 'docker://busybox'},
                {'id': 'sha512-XXX',
                 'path': 'path/to/image.aci', 'signature': 'image.aci.asc'},
            ],
            manifest={},
        ))
        self.assertEqual(3, len(pod.images))
        self.assertObjectFields(
            dict(uri='http://localhost/image.aci', signature=None),
            pod.images[0],
        )
        self.assertObjectFields(
            dict(uri='docker://busybox', signature=None),
            pod.images[1],
        )
        self.assertObjectFields(
            dict(
                path=Path(__file__).parent / 'path/to/image.aci',
                signature=Path(__file__).parent / 'image.aci.asc',
            ),
            pod.images[2],
        )

    def test_volume(self):
        pod = models.Pod(Path(__file__), dict(
            name='xy',
            version=1001,
            volumes=[dict(name='x', data='y')],
            manifest={},
        ))
        self.assertEqual(1, len(pod.volumes))
        self.assertObjectFields(
            dict(name='x', path=Path(__file__).parent / 'y'),
            pod.volumes[0],
        )

    def test_ports(self):
        ports = models.Ports([])
        self.assertEqual([], list(ports))
        self.assertEqual(-1, ports._last_port)
        self.assertEqual(30000, ports.next_available_port())

        ports = models.Ports([
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
            models.Ports([
                ('p1', 1, {'ports': [{'name': 'tcp', 'hostPort': 30011}]}),
                ('p2', 3, {'ports': [{'name': 'tcp', 'hostPort': 30011}]}),
            ])

    def assertObjectFields(self, expect, actual):
        for name, value in expect.items():
            self.assertEqual(value, getattr(actual, name))


if __name__ == '__main__':
    unittest.main()
