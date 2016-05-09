"""Build http2."""

from foreman import define_rule
from shipyard import (
    python_build_package,
    python_copy_package,
    python_pip_install,
)


(define_rule('build')
 .with_doc(__doc__)
 .with_build(lambda ps: (
     python_pip_install(ps, 'cython'),
     python_build_package(ps, 'http2'),
 ))
 .depend('//shipyard/cpython:build')
 .depend('//shipyard/nghttp2:build')
)


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: python_copy_package(ps, 'http2'))
 .depend('build')
 .depend('//shipyard/nghttp2:tapeout')
 .reverse_depend('//shipyard/cpython:final_tapeout')
)
