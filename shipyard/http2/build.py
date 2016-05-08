"""Build http2."""

from foreman import define_rule
from shipyard import (
    python_build_package,
    python_copy_package,
    python_pip_install,
)


(define_rule('http2')
 .with_doc(__doc__)
 .with_build(lambda ps: (
     python_pip_install(ps, 'cython'),
     python_build_package(ps, 'http2'),
 ))
 .depend('//shipyard/cpython:cpython')
 .depend('//shipyard/nghttp2:nghttp2')
)


(define_rule('build_image')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: python_copy_package(ps, 'http2'))
 .depend('//shipyard/cpython:build_image')
 .depend('//shipyard/nghttp2:build_image')
 .depend('http2')
)
