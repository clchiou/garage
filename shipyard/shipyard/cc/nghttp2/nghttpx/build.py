"""Build nghttp2 from source - nghttpx."""

from foreman import define_rule
from shipyard import (
    render_appc_manifest,
    tapeout_files,
    tapeout_libraries,
)


(define_rule('build')
 .with_doc(__doc__)
 .depend('//base:build')
 .depend('//cc/nghttp2:build')
)


(define_rule('tapeout')
 .with_build(lambda ps: (
     tapeout_files(ps, ['/usr/local/bin/nghttpx']),
     tapeout_libraries(ps, '/usr/lib/x86_64-linux-gnu', [
         'libev',
         'libjemalloc',
         'libstdc++',
     ]),
     render_appc_manifest(ps, 'templates/manifest'),
 ))
 .depend('build')
 .depend('//cc/nghttp2:tapeout')
 .depend('//host/mako:install')
 .reverse_depend('//base:tapeout')
)


(define_rule('build_image')
 .with_doc("""Build containerized image.""")
 .depend('tapeout')
 .depend('//base:build_image')
)
