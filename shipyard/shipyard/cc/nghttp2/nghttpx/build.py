"""Build nghttp2 from source - nghttpx."""

from foreman import define_parameter, define_rule
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


def make_image_manifest(_, base_manifest, *, exec_args=None, ports=None):
    if not ports:
        ports = [{'name': 'http', 'protocol': 'tcp', 'port': 8000}]
    return combine_dicts(
        base_manifest,
        {
            'app': {
                'exec': ['/usr/local/bin/nghttpx'] + list(exec_args or ()),
                'user': 'nobody',
                'group': 'nogroup',
                'environment': [
                    {
                        'name': 'LD_LIBRARY_PATH',
                        'value': '/usr/local/lib'
                    },
                ],
                'workingDirectory': '/',
                'ports': ports,
            },
        },
    )


pod.define_image(pod.Image(
    name='nghttpx',
    make_manifest=make_image_manifest,
    depends=[
        'tapeout',
    ],
))


(define_parameter('make_image_manifest')
 .with_doc("""Expose make_image_manifest for nghttpx user.""")
 .with_default(make_image_manifest)
)
