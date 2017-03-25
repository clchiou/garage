import unittest

from pathlib import Path

from ops import models


class ModelsTest(unittest.TestCase):

    def test_pod(self):

        pod_path = Path(__file__).parent

        with self.assertRaisesRegex(KeyError, 'name'):
            models.Pod({}, pod_path)
        with self.assertRaisesRegex(KeyError, 'version'):
            models.Pod({'name': 'example'}, pod_path)
        with self.assertRaisesRegex(
                ValueError, 'invalid name for \'name\': x--y'):
            models.Pod({'name': 'x--y', 'version': 1001}, pod_path)
        with self.assertRaisesRegex(ValueError, 'unknown field \'x\''):
            models.Pod({'name': 'x-y', 'version': 1, 'x': 1}, pod_path)

        pod = models.Pod(
            dict(
                name='xy',
                version=1001,
                manifest={},
            ),
            pod_path,
        )
        self.assertEqual('xy:1001', str(pod))
        self.assertObjectFields(
            dict(
                path=pod_path,
                name='xy',
                version='1001',
                systemd_units=(),
                images=(),
                volumes=(),
                manifest={},
            ),
            pod,
        )

    def test_systemd_unit(self):

        pod_data = {
            'name': 'xy',
            'version': '1001',
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
        }
        pod_path = Path(__file__).parent
        pod = models.Pod(pod_data, pod_path)

        self.assertEqual(6, len(pod.systemd_units))
        self.assertObjectFields(
            dict(
                unit_file_path=pod_path / 'example.service',
                unit_name='xy-example-1001.service',
                instances=(),
                unit_path=Path('/etc/systemd/system/xy-example-1001.service'),
                dropin_path=Path(
                    '/etc/systemd/system/xy-example-1001.service.d'),
            ),
            pod.systemd_units[0],
        )
        self.assertObjectFields(
            dict(
                unit_file_path=pod_path / 'sample.timer',
                unit_name='xy-sample-1001.timer',
                instances=(),
            ),
            pod.systemd_units[1],
        )
        self.assertObjectFields(
            dict(
                unit_name='xy-example-1001@.service',
                instances=(
                    'xy-example-1001@0.service',
                ),
            ),
            pod.systemd_units[2],
        )
        self.assertObjectFields(
            dict(
                unit_name='xy-example-1001@.service',
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
                unit_name='xy-example-1001@.service',
                instances=(
                    'xy-example-1001@8000.service',
                ),
            ),
            pod.systemd_units[4],
        )
        self.assertObjectFields(
            dict(
                unit_name='xy-example-1001@.service',
                instances=(
                    'xy-example-1001@a.service',
                    'xy-example-1001@b.service',
                    'xy-example-1001@c.service',
                ),
            ),
            pod.systemd_units[5],
        )

        with self.assertRaisesRegex(ValueError, 'invalid instances: 0'):
            pod_data = {
                'name': 'xy',
                'version': '1001',
                'systemd-units': [
                    {
                        'unit-file': 'example.service',
                        'instances': 0,
                    },
                ],
                'manifest': {},
            }
            pod = models.Pod(pod_data, pod_path)

    def test_image(self):
        pod_data = dict(
            name='xy',
            version='1.0.1',
            images=[
                {'id': 'sha512-XXX', 'image': 'http://localhost/image.aci'},
                {'id': 'sha512-XXX', 'image': 'docker://busybox'},
                {'id': 'sha512-XXX',
                 'image': 'path/to/image.aci',
                 'signature': 'image.aci.asc'},
            ],
            manifest={},
        )
        pod_path = Path(__file__).parent
        pod = models.Pod(pod_data, pod_path)

        self.assertEqual(3, len(pod.images))
        self.assertObjectFields(
            dict(
                image_path=None,
                image_uri='http://localhost/image.aci',
                signature_path=None,
                signature_uri=None,
            ),
            pod.images[0],
        )
        self.assertObjectFields(
            dict(
                image_path=None,
                image_uri='docker://busybox',
                signature_path=None,
                signature_uri=None,
            ),
            pod.images[1],
        )
        self.assertObjectFields(
            dict(
                image_path=pod_path / 'path/to/image.aci',
                image_uri=None,
                signature_path=pod_path / 'image.aci.asc',
                signature_uri=None,
            ),
            pod.images[2],
        )

    def test_volume(self):
        pod_data = dict(
            name='xy',
            version=1001,
            volumes=[dict(name='x', data='y')],
            manifest={},
        )
        pod_path = Path(__file__).parent
        pod = models.Pod(pod_data, pod_path)

        self.assertEqual(1, len(pod.volumes))
        self.assertObjectFields(
            dict(name='x', data_path=pod_path / 'y'),
            pod.volumes[0],
        )

    def assertObjectFields(self, expect, actual):
        for name, value in expect.items():
            self.assertEqual(value, getattr(actual, name))


if __name__ == '__main__':
    unittest.main()
