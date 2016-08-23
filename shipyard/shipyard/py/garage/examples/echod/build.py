from shipyard import pod, py


NAME = 'echod'
PATH = 'py/garage/examples/echod'


py.define_package(
    package_name=NAME,
    derive_src_path=lambda ps: ps['//base:root'] / PATH,
    derive_build_src_path=lambda ps: ps['//base:build'] / PATH,
    build_rule_deps=[
        '//py/garage:build',
        '//py/http2:build',
        '//py/startup:build',
    ],
    tapeout_rule_deps=[
        '//py/garage:tapeout',
        '//py/http2:tapeout',
        '//py/startup:tapeout',
    ],
)


def make_image_manifest(parameters, base_manifest):
    manifest = py.make_manifest(parameters, base_manifest)
    app = manifest['app']
    app['exec'].extend(['-m', 'echod', '--port', '8000'])
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
    name='echod',
    systemd_units=[
        pod.SystemdUnit(
            unit_file='files/echod.service',
            start=True,
        ),
    ],
    apps=[
        pod.App(
            name='echod',
            image_name='echod',
        ),
    ],
    images=[
        pod.Image(
            name='echod',
            make_manifest=make_image_manifest,
            depends=[
                'tapeout',
                '//base:tapeout',
                '//py/cpython:tapeout',
            ],
        ),
    ],
))
