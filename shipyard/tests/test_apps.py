import unittest

from templates import apps

if __name__ == '__main__':
    from fixtures import PrepareForeman
else:
    from .fixtures import PrepareForeman


class AppTest(PrepareForeman, unittest.TestCase):

    TEST_IMAGE = apps.Image(
        name='example.com/worker',
        app=apps.App(
            name='worker',
            exec=['/bin/bash'],
            environment={
                'PATH': '/bin:/usr/bin',
            },
            volumes=[
                apps.Volume(
                    name='data',
                    path='/var/data',
                ),
                apps.Volume(
                    name='log',
                    path='/var/log',
                    read_only=False,
                ),
            ],
        ),
    )

    TEST_IMAGE._id = 'sha512-...'

    APP_ENTRY = {
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
                'path': '/var/log',
                'readOnly': False,
            },
        ],
    }

    IMAGE_MANIFEST = {
        'acKind': 'ImageManifest',
        'acVersion': '0.8.10',
        'name': 'example.com/worker',
        'labels': [
            {
                'name': 'arch',
                'value': 'amd64',
            },
            {
                'name': 'os',
                'value': 'linux',
            },
        ],
        'app': APP_ENTRY,
    }

    TEST_POD = apps.Pod(
        name='application',
        images=[TEST_IMAGE],
    )

    TEST_POD._version = 1

    POD_MANIFEST = {
        'acVersion': '0.8.10',
        'acKind': 'PodManifest',
        'apps': [
            {
                'name': 'worker',
                'image': {
                    'name': 'example.com/worker',
                    'id': 'sha512-...',
                },
                'app': APP_ENTRY,
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
                'readOnly': False,
                'recursive': True,
            },
        ],
    }

    POD_OBJECT = {
        'name': 'application',
        'version': 1,
        'systemd-units': [],
        'images': [
            {
                'id': 'sha512-...',
                'path': 'example.com/worker/image.aci',
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
        'manifest': POD_MANIFEST,
    }

    def test_image(self):
        self.assertEqual(self.IMAGE_MANIFEST, self.TEST_IMAGE.image_manifest)

    def test_pod(self):
        self.assertEqual(self.POD_MANIFEST, self.TEST_POD.pod_manifest)
        self.assertEqual(self.POD_OBJECT, self.TEST_POD.pod_object)


if __name__ == '__main__':
    unittest.main()
