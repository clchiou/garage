import unittest

from pathlib import Path
import copy

from ops import models


class ModelsTest(unittest.TestCase):

    def test_pod(self):

        pod_path = Path(__file__).parent

        with self.assertRaisesRegex(KeyError, 'name'):
            models.Pod({}, pod_path)
        with self.assertRaisesRegex(KeyError, 'version'):
            models.Pod({'name': '//foo:bar'}, pod_path)
        with self.assertRaisesRegex(
                ValueError, 'invalid pod name for \'name\': //a:x--y'):
            models.Pod({'name': '//a:x--y', 'version': 1001}, pod_path)
        with self.assertRaisesRegex(
                ValueError, 'invalid pod name for \'name\': //a--b:x-y'):
            models.Pod({'name': '//a--b:x-y', 'version': 1001}, pod_path)
        with self.assertRaisesRegex(
                ValueError, 'invalid pod name for \'name\': xy'):
            models.Pod({'name': 'xy', 'version': 1001}, pod_path)
        with self.assertRaisesRegex(
                ValueError, 'invalid pod name for \'name\': //a/b:'):
            models.Pod({'name': '//a/b:', 'version': 1001}, pod_path)
        with self.assertRaisesRegex(ValueError, 'unknown field \'x\''):
            models.Pod({'name': 'x-y', 'version': 1, 'x': 1}, pod_path)

        pod = models.Pod(
            dict(
                name='//ab:xy',
                version=1001,
                manifest={},
            ),
            pod_path,
        )
        self.assertEqual('//ab:xy@1001', str(pod))
        self.assertObjectFields(
            dict(
                path=pod_path,
                name='//ab:xy',
                version='1001',
                systemd_units=(),
                images=(),
                volumes=(),
                ports=(),
                manifest={},
            ),
            pod,
        )

    def test_make_local_pod(self):
        bundle_pod_path = Path('/path/to/bundle')
        bundle_pod = models.Pod(
            {
                'name': '//foo/bar:example',
                'version': '1.0.1',
                'systemd-units': [
                    {
                        'unit-file': 'path/to/foo.service',
                        'checksum': 'sha512-123',
                        'instances': [1, 2, 3],
                    },
                    {
                        'unit-file': 'http://host/path/to/bar.service?x=1',
                        'enable': False,
                        'start': False,
                        'checksum': 'sha512-456',
                    },
                ],
                'images': [
                    {
                        'id': 'sha512-01234567890123456789',
                        'image': 'path/to/image-1.aci',
                        'signature': 'path/to/image-1.aci.asc',
                    },
                    {
                        'id': 'sha512-abc',
                        'image': 'http://host/path/to/image-2.aci',
                    },
                ],
                'volumes': [
                    {
                        'name': 'volume-1',
                        'user': 'plumber',
                        'group': 'plumber',
                        'data': 'path/to/data.tar.bz2',
                        'checksum': 'sha512-def',
                    },
                    {
                        'name': 'volume-2',
                        'data': 'http://host/path/to/data.tar.gz?y=3',
                        'checksum': 'sha512-ghi',
                    },
                ],
                'ports': [
                    {
                        'name': 'web',
                        'host-ports': [443],
                    },
                ],
                'manifest': {
                    'some-key': 'some-value',
                },
            },
            bundle_pod_path,
        )

        reloaded = models.Pod(
            copy.deepcopy(bundle_pod.to_pod_data()),
            bundle_pod_path,
        )
        self.assertEqual(bundle_pod.to_pod_data(), reloaded.to_pod_data())

        pod_path = Path(__file__).parent
        pod = bundle_pod.make_local_pod(pod_path)

        # Make sure we did't alter the original in make_local_pod()
        self.assertEqual(bundle_pod.to_pod_data(), reloaded.to_pod_data())

        self.assertEqual(
            {
                'name': '//foo/bar:example',
                'version': '1.0.1',
                'systemd-units': [
                    {
                        'name': 'foo',
                        'unit-file':
                        'systemd/foo--bar--example--foo--1.0.1@.service',
                        'enable': True,
                        'start': True,
                        'checksum': 'sha512-123',
                        'instances': [1, 2, 3],
                    },
                    {
                        'name': 'bar',
                        'unit-file':
                        'systemd/foo--bar--example--bar--1.0.1.service',
                        'enable': False,
                        'start': False,
                        'checksum': 'sha512-456',
                    },
                ],
                'images': [
                    {
                        'id': 'sha512-01234567890123456789',
                        'image': 'images/sha512-0123456789012345.aci',
                        'signature': 'images/sha512-0123456789012345.aci.asc',
                    },
                    {
                        'id': 'sha512-abc',
                        'image': 'http://host/path/to/image-2.aci',
                    },
                ],
                'volumes': [
                    {
                        'name': 'volume-1',
                        'user': 'plumber',
                        'group': 'plumber',
                        'data': 'volume-data/volume-1.tar.bz2',
                        'checksum': 'sha512-def',
                    },
                    {
                        'name': 'volume-2',
                        'data': 'volume-data/volume-2.tar.gz',
                        'checksum': 'sha512-ghi',
                    },
                ],
                'ports': [
                    {
                        'name': 'web',
                        'host-ports': [443],
                    },
                ],
                'manifest': {
                    'some-key': 'some-value',
                },
            },
            pod.to_pod_data(),
        )

        self.assertEqual(
            pod_path / 'systemd/foo--bar--example--foo--1.0.1@.service',
            pod.systemd_units[0].unit_file_path,
        )
        self.assertEqual(
            pod_path / 'systemd/foo--bar--example--bar--1.0.1.service',
            pod.systemd_units[1].unit_file_path,
        )

        self.assertEqual(
            pod_path / 'images/sha512-0123456789012345.aci',
            pod.images[0].image_path,
        )
        self.assertEqual(
            pod_path / 'images/sha512-0123456789012345.aci.asc',
            pod.images[0].signature,
        )

        self.assertEqual(
            pod_path / 'volume-data/volume-1.tar.bz2',
            pod.volumes[0].data_path,
        )
        self.assertEqual(
            pod_path / 'volume-data/volume-2.tar.gz',
            pod.volumes[1].data_path,
        )

    def test_systemd_unit(self):

        pod_data = {
            'name': '//x:y',
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
                    'unit-file': 'example@.service',
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
                unit_name='x--y--example--1001.service',
                _instances=(),
                unit_path=
                Path('/etc/systemd/system/x--y--example--1001.service'),
            ),
            pod.systemd_units[0],
        )
        self.assertObjectFields(
            dict(
                unit_file_path=pod_path / 'sample.timer',
                unit_name='x--y--sample--1001.timer',
                _instances=(),
            ),
            pod.systemd_units[1],
        )
        self.assertObjectFields(
            dict(
                unit_name='x--y--example--1001@.service',
                _instances=1,
            ),
            pod.systemd_units[2],
        )
        self.assertObjectFields(
            dict(
                unit_name='x--y--example--1001@.service',
                _instances=3,
            ),
            pod.systemd_units[3],
        )
        self.assertObjectFields(
            dict(
                unit_name='x--y--example--1001@.service',
                _instances=[8000],
            ),
            pod.systemd_units[4],
        )
        self.assertObjectFields(
            dict(
                unit_name='x--y--example--1001@.service',
                _instances=['a', 'b', 'c'],
            ),
            pod.systemd_units[5],
        )
        self.assertEqual(
            [
                'x--y--example--1001@a.service',
                'x--y--example--1001@b.service',
                'x--y--example--1001@c.service',
            ],
            [
                instance.unit_name
                for instance in pod.systemd_units[5].instances
            ],
        )

        with self.assertRaisesRegex(AssertionError, 'expect 0 >= 1'):
            models.SystemdUnit(
                {'unit-file': 'example.service', 'instances': 0}, pod)

        with self.assertRaisesRegex(ValueError, 'path is absolute'):
            models.SystemdUnit(
                {'unit-file': '/path/to/example.service'}, pod)

        with self.assertRaisesRegex(ValueError, 'unsupported uri scheme'):
            models.SystemdUnit(
                {'unit-file': 'docker://host/example.service'}, pod)

    def test_image(self):
        pod_data = dict(
            name='//x:y',
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
                signature=None,
            ),
            pod.images[0],
        )
        self.assertObjectFields(
            dict(
                image_path=None,
                image_uri='docker://busybox',
                signature=None,
            ),
            pod.images[1],
        )
        self.assertObjectFields(
            dict(
                image_path=pod_path / 'path/to/image.aci',
                image_uri=None,
                signature=pod_path / 'image.aci.asc',
            ),
            pod.images[2],
        )

        with self.assertRaisesRegex(ValueError, 'path is absolute'):
            models.Image({'id': '', 'image': '/xyz'}, pod)

        with self.assertRaisesRegex(ValueError, 'unsupported uri scheme'):
            models.Image({'id': '', 'image': 'ftp://xyz'}, pod)

    def test_instance_resolve_specifier(self):

        instance = models.SystemdUnit.Instance(
            name=None, unit_name='foo.service', enable=True, start=True)
        self.assertEqual('%i', instance.resolve_specifier('%i'))

        instance = models.SystemdUnit.Instance(
            name='bar', unit_name='foo@.service', enable=True, start=True)
        self.assertEqual('', instance.resolve_specifier(''))
        self.assertEqual('spam\negg', instance.resolve_specifier('spam\negg'))
        self.assertEqual('bar\nbar', instance.resolve_specifier('%i\n%i'))
        self.assertEqual('bar', instance.resolve_specifier('%i'))
        self.assertEqual('%%i', instance.resolve_specifier('%%i'))
        self.assertEqual('%%bar', instance.resolve_specifier('%%%i'))
        self.assertEqual('%%%%i', instance.resolve_specifier('%%%%i'))
        self.assertEqual('%%%%bar', instance.resolve_specifier('%%%%%i'))

    def test_volume(self):
        pod_data = dict(
            name='//x:y',
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

        with self.assertRaisesRegex(ValueError, 'path is absolute'):
            models.Volume({'name': 'xyz', 'data': '/xyz'}, pod)

        with self.assertRaisesRegex(ValueError, 'unsupported uri scheme'):
            models.Volume({'name': 'xyz', 'data': 'docker://xyz'}, pod)

    def assertObjectFields(self, expect, actual):
        for name, value in expect.items():
            self.assertEqual(value, getattr(actual, name))


if __name__ == '__main__':
    unittest.main()
