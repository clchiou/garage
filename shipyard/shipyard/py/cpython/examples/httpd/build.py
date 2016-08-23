from shipyard import pod, py


WWW_PATH = '/var/www'


def make_image_manifest(parameters, base_manifest):
    manifest = py.make_manifest(parameters, base_manifest)
    app = manifest['app']
    app['exec'].extend(['-m', 'http.server', '8000'])
    app['workingDirectory'] = WWW_PATH
    app['ports'] = [
        {
            'name': 'http',
            'protocol': 'tcp',
            'port': 8000,
            'count': 1,
            'socketActivated': False,
        },
    ]
    return manifest


pod.define_pod(pod.Pod(
    name='httpd',
    systemd_units=[
        pod.SystemdUnit(
            unit_file='files/httpd.service',
            start=True,
        ),
    ],
    apps=[
        pod.App(
            name='httpd',
            image_name='httpd',
            volume_names=[
                'www',
            ],
        ),
    ],
    images=[
        pod.Image(
            name='httpd',
            make_manifest=make_image_manifest,
            depends=[
                '//base:tapeout',
                '//py/cpython:tapeout',
            ],
        ),
    ],
    volumes=[
        pod.Volume(
            name='www',
            path=WWW_PATH,
            data='data.tgz',
        ),
    ],
    files=[
        'files/data.tgz',
    ],
))
