import unittest

from templates import pods

from tests.fixtures import PrepareForeman


class AppTest(PrepareForeman, unittest.TestCase):

    TEST_APP = pods.App(
        name='worker',
        exec=['/bin/bash'],
        environment={
            'PATH': '/bin:/usr/bin',
        },
        volumes=[
            pods.Volume(
                name='data',
                path='/var/data',
            ),
            pods.Volume(
                name='log',
                path='/var/log/host',
                read_only=False,
                host_path='/var/log',
            ),
        ],
        ports=[
            pods.Port(
                name='https',
                protocol='tcp',
                port=443,
                host_port=443,
            ),
            pods.Port(
                name='health',
                protocol='udp',
                port=40000,
            ),
            pods.Port(
                name='ftp',
                protocol='udp',
                port=21,
                host_ports=(1021, 1022, 1023),
            ),
        ],
        extra_app_entry_fields={
            'isolators': [],
        },
    )

    TEST_IMAGE = pods.Image(
        name='example.com/worker-image',
        app=TEST_APP,
    )

    TEST_IMAGE._id = 'sha512-...'
    TEST_IMAGE._version = 'image-version-1'

    APP_ENTRY_1 = {
        'exec': ['/bin/bash'],
        'user': 'nobody',
        'group': 'nogroup',
        'workingDirectory': '/',
        'environment': [
            {
                'name': 'PATH',
                'value': '/bin:/usr/bin',
            },
        ],
        'mountPoints': [
            {
                'name': 'data',
                'path': '/var/data',
                'readOnly': True,
            },
            {
                'name': 'log',
                'path': '/var/log/host',
                'readOnly': False,
            },
        ],
        'ports': [
            {
                'name': 'https',
                'port': 443,
                'protocol': 'tcp',
            },
            {
                'name': 'health',
                'port': 40000,
                'protocol': 'udp',
            },
            {
                'name': 'ftp',
                'port': 21,
                'protocol': 'udp',
            },
        ],
        'isolators': [],
    }

    APP_ENTRY_2 = {
        'exec': ['/bin/bash'],
        'user': 'nobody',
        'group': 'nogroup',
        'workingDirectory': '/',
        'environment': [
            {
                'name': 'PATH',
                'value': '/bin:/usr/bin',
            },
        ],
        'mountPoints': [
            {
                'name': 'data',
                'path': '/var/data',
                'readOnly': True,
            },
            {
                'name': 'log',
                'path': '/var/log/host',
                'readOnly': False,
            },
            {
                'name': 'example.com/worker-image--tmp',
                'path': '/tmp',
                'readOnly': False,
            },
        ],
        'ports': [
            {
                'name': 'https',
                'port': 443,
                'protocol': 'tcp',
            },
            {
                'name': 'health',
                'port': 40000,
                'protocol': 'udp',
            },
            {
                'name': 'ftp',
                'port': 21,
                'protocol': 'udp',
            },
        ],
        'isolators': [],
    }

    IMAGE_MANIFEST = {
        'acKind': 'ImageManifest',
        'acVersion': '0.8.10',
        'name': 'example.com/worker-image',
        'labels': [
            {
                'name': 'arch',
                'value': 'amd64',
            },
            {
                'name': 'os',
                'value': 'linux',
            },
            {
                'name': 'version',
                'value': 'image-version-1',
            },
        ],
        'app': APP_ENTRY_1,
    }

    TEST_SYSTEMD_UNIT = pods.SystemdUnit(
        unit_file='foo.service',
        instances=[1, 2, 3],
    )

    TEST_POD = pods.Pod(
        name='application',
        images=[TEST_IMAGE],
        systemd_units=[TEST_SYSTEMD_UNIT],
    )

    TEST_POD._version = 'pod-version-1'

    POD_MANIFEST = {
        'acVersion': '0.8.10',
        'acKind': 'PodManifest',
        'apps': [
            {
                'name': 'worker',
                'image': {
                    'name': 'example.com/worker-image',
                    'id': 'sha512-...',
                },
                'app': APP_ENTRY_2,
                'readOnlyRootFS': True,
            },
        ],
        'volumes': [
            {
                'name': 'data',
                'kind': 'host',
                'readOnly': True,
                'recursive': True,
            },
            {
                'name': 'log',
                'kind': 'host',
                'source': '/var/log',
                'readOnly': False,
                'recursive': True,
            },
            {
                'name': 'example.com/worker-image--tmp',
                'kind': 'empty',
                'readOnly': False,
                'recursive': True,
                'mode': '1777',
            },
        ],
        'ports': [
            {
                'name': 'https',
                'hostPort': 443,
            },
        ],
    }

    POD_OBJECT = {
        'name': 'application',
        'version': 'pod-version-1',
        'systemd-units': [
            {
                'unit-file': 'foo.service',
                'enable': True,
                'start': True,
                'instances': [1, 2, 3],
            },
        ],
        'images': [
            {
                'id': 'sha512-...',
                'image': 'example.com/worker-image/image.aci',
            },
        ],
        'volumes': [
            {
                'name': 'data',
                'user': 'nobody',
                'group': 'nogroup',
            },
            {
                'name': 'log',
                'user': 'nobody',
                'group': 'nogroup',
            },
        ],
        'ports': [
            {
                'name': 'ftp',
                'host-ports': [1021, 1022, 1023],
            },
        ],
        'manifest': POD_MANIFEST,
    }

    def test_model_object_methods(self):
        dict_1 = pods.App.to_dict(self.TEST_APP)
        dict_2 = pods.App.to_dict(pods.App.from_dict(dict_1))
        self.assertEqual(dict_1, dict_2)

        dict_1 = pods.Image.to_dict(self.TEST_IMAGE)
        dict_2 = pods.Image.to_dict(pods.Image.from_dict(dict_1))
        self.assertEqual(dict_1, dict_2)

        dict_1 = pods.Pod.to_dict(self.TEST_POD)
        dict_2 = pods.Pod.to_dict(pods.Pod.from_dict(dict_1))
        self.assertEqual(dict_1, dict_2)

    def test_image(self):
        self.assertEqual(
            self.IMAGE_MANIFEST,
            self.TEST_IMAGE.get_image_manifest(),
        )

    def test_pod(self):
        self.assertEqual(
            self.POD_MANIFEST,
            self.TEST_POD.get_pod_manifest(),
        )
        self.assertEqual(
            self.POD_OBJECT,
            self.TEST_POD.get_pod_object(),
        )


if __name__ == '__main__':
    unittest.main()
