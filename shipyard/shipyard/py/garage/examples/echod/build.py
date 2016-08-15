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


pod.define_pod(pod.Pod(
    name='echod',
    template_files=[
        '//base:templates/pod.json',
    ],
    make_template_vars=lambda ps: {'unit_files': ['echod.service']},
    files=[
        'files/echod.service',
    ],
    images=[
        pod.Image(
            name='echod',
            manifest='//py/cpython:templates/manifest',
            depends=[
                'tapeout',
                '//base:tapeout',
                '//py/cpython:tapeout',
            ],
        ),
    ],
))
