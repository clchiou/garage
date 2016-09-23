import unittest

from pathlib import Path

from ops.pods import models


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

    def assertObjectFields(self, expect, actual):
        for name, value in expect.items():
            self.assertEqual(value, getattr(actual, name))


if __name__ == '__main__':
    unittest.main()
