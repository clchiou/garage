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
 .depend('//host/mako:install')
 .reverse_depend('//base:tapeout')
)


pod.define_image(pod.Image(
    name='nghttpx',
    manifest='templates/manifest',
    depends=[
        'tapeout',
    ],
))
