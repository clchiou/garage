from foreman import decorate_rule, to_path
from shipyard import pod, py, tar_create


WWW_PATH = '/var/www'
WWW_DATA = 'data.tar.gz'


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


@decorate_rule('//base:build')
def build_data(parameters):
    tar_create(
        to_path('index.html').parent,
        ['index.html'],
        parameters['//base:output'] / WWW_DATA,
        tar_extra_flags=['--gzip'],
    )


pod.define_pod(pod.Pod(
    name='httpd',
    systemd_units=[
        pod.SystemdUnit(
            unit_file='httpd.service',
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
            data=WWW_DATA,
        ),
    ],
    depends=[
        'build_data',
    ],
))
