"""Build nghttp2 from source - nghttpx."""

from foreman import define_rule
from shipyard import (
    combine_dicts,
    pod,
    tapeout_files,
    tapeout_libraries,
)


(define_rule('tapeout')
 .with_build(lambda ps: (
     tapeout_files(ps, ['/usr/local/bin/nghttpx']),
     tapeout_libraries(ps, '/usr/lib/x86_64-linux-gnu', [
         'libev',
         'libjemalloc',
         'libstdc++',
     ]),
 ))
 .depend('//cc/nghttp2:tapeout')
 .reverse_depend('//base:tapeout')
)


pod.define_image(pod.Image(
    name='nghttpx',
    make_manifest=lambda ps, base_manifest: combine_dicts(
        base_manifest,
        {
            'app': {
                'exec': [
                    '/usr/local/bin/nghttpx',
                ],
                'user': 'nobody',
                'group': 'nobody',
                'environment': [
                    {
                        'name': 'LD_LIBRARY_PATH',
                        'value': '/usr/local/lib'
                    },
                ],
                'workingDirectory': '/',
                'ports': [
                    {
                        'name': 'http',
                        'protocol': 'tcp',
                        'port': 8000,
                        'count': 1,
                        'socketActivated': False,
                    },
                ],
            },
        },
    ),
    depends=[
        'tapeout',
    ],
))
