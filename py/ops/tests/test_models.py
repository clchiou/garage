import unittest

from pathlib import Path

from ops.apps import models


class ModelsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.testdata_path = Path(__file__).parent / 'testdata'
        assert cls.testdata_path.is_dir()

    def test_pod_load_json(self):
        with self.assertRaisesRegex(
                ValueError,
                r'^no ops annotation: .*/testdata/pod-none.json$'):
            models.Pod.load_json(self.testdata_path / 'pod-none.json')
        with self.assertRaisesRegex(
                ValueError,
                r'^multiple ops annotations: .*/testdata/pod-multiple.json$'):
            models.Pod.load_json(self.testdata_path / 'pod-multiple.json')

    def test_pod(self):
        with self.assertRaisesRegex(KeyError, 'name'):
            models.Pod(self.testdata_path, {})
        with self.assertRaisesRegex(KeyError, 'version'):
            models.Pod(self.testdata_path, {'name': 'example'})
        with self.assertRaisesRegex(ValueError, 'invalid pod name: x--y'):
            models.Pod(self.testdata_path, {'name': 'x--y', 'version': 1001})
        with self.assertRaisesRegex(ValueError, 'invalid literal for int'):
            models.Pod(self.testdata_path, {'name': 'x-y', 'version': 'z'})
        with self.assertRaisesRegex(ValueError, 'unknown names: x'):
            models.Pod(
                self.testdata_path, {'name': 'x-y', 'version': 1001, 'x': 1})

        pod = models.Pod(self.testdata_path, {'name': 'xy', 'version': 1001})
        self.assertEqual('xy:1001', str(pod))
        self.assertObjectFields(
            dict(
                path=self.testdata_path.absolute(),
                name='xy',
                version=1001,
                systemd_units=(),
                images=(),
                volumes=(),
            ),
            pod,
        )

    def test_systemd_unit(self):
        pod = models.Pod(self.testdata_path, {
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
        })
        self.assertEqual(6, len(pod.systemd_units))
        self.assertObjectFields(
            dict(
                path=self.testdata_path.parent / 'example.service',
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
                path=self.testdata_path.parent / 'sample.timer',
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
        pod = models.Pod(self.testdata_path, dict(
            name='xy',
            version=1001,
            images=[
                {'uri': 'http://localhost/image.aci'},
                {'uri': 'docker://busybox'},
                {'path': 'path/to/image.aci',
                 'signature': 'image.aci.asc'},
            ],
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
                path=self.testdata_path.parent / 'path/to/image.aci',
                signature=self.testdata_path.parent / 'image.aci.asc',
            ),
            pod.images[2],
        )

    def test_volume(self):
        pod = models.Pod(self.testdata_path, dict(
            name='xy',
            version=1001,
            volumes=[dict(volume='x', data='y')],
        ))
        self.assertEqual(1, len(pod.volumes))
        self.assertObjectFields(
            dict(volume='x', path=self.testdata_path.parent / 'y'),
            pod.volumes[0],
        )

    def assertObjectFields(self, expect, actual):
        for name, value in expect.items():
            self.assertEqual(value, getattr(actual, name))


if __name__ == '__main__':
    unittest.main()
