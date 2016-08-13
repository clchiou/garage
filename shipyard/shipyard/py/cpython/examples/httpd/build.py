from shipyard import pod


WWW_PATH = '/var/www'


pod.define_pod(pod.Pod(
    name='httpd',
    template_files=[
        '//base:templates/pod.json',
        'templates/httpd.service',
    ],
    make_template_vars=lambda ps: {'unit_files': ['httpd.service']},
    files=[
        'data.tgz',
    ],
    images=[
        pod.Image(
            name='httpd',
            manifest='//py/cpython:templates/manifest',
            make_template_vars=lambda ps: {'working_directory': WWW_PATH},
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
))
