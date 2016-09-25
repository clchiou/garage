from foreman import decorate_rule, to_path
from shipyard import pod, py, tar_create


WWW_PATH = '/var/www'
WWW_DATA = 'data.tar.gz'


def _make_image_manifest(parameters, manifest):
    manifest = py.make_manifest(parameters, manifest)
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


pod.define_image(pod.Image(
    label_name='httpd',
    make_manifest=_make_image_manifest,
    depends=[
        '//base:tapeout',
        '//py/cpython:tapeout',
    ],
))


@decorate_rule('//base:build')
def build_data(parameters):
    tar_create(
        to_path('index.html').parent,
        ['index.html'],
        parameters['//base:output'] / WWW_DATA,
        tar_extra_flags=['--gzip'],
    )


pod.define_pod(pod.Pod(
    label_name='httpd',
    systemd_units=[
        pod.SystemdUnit(unit_file='httpd.service'),
    ],
    apps=[
        pod.App(
            name='httpd',
            image_label='image/httpd',
            volume_names=[
                'www',
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
