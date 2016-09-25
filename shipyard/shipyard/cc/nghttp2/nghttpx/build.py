"""Build nghttp2 from source - nghttpx."""

from foreman import define_rule
from shipyard import (
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


def make_image_manifest(_, manifest):
    assert 'app' not in manifest
    manifest['app'] = {
        'exec': ['/usr/local/bin/nghttpx'],
        'user': 'nobody',
        'group': 'nogroup',
        'environment': [
            {
                'name': 'LD_LIBRARY_PATH',
                'value': '/usr/local/lib'
            },
        ],
        'workingDirectory': '/',
    }
    return manifest


pod.define_image(pod.Image(
    label_name='nghttpx',
    make_manifest=make_image_manifest,
    depends=[
        'tapeout',
    ],
))
