"""Build http2."""

from foreman import define_rule
from shipyard import (
    python_copy_and_build_package,
    python_copy_package,
    python_pip_install,
)


(define_rule('build')
 .with_doc(__doc__)
 .with_build(lambda ps: (
     python_pip_install(ps, 'cython'),
     python_copy_and_build_package(ps, 'http2'),
 ))
 .depend('//base:build')
 .depend('//cpython:build')
 .depend('//nghttp2:build')
)


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: python_copy_package(ps, 'http2'))
 .depend('build')
 .depend('//nghttp2:tapeout')
 .reverse_depend('//base:tapeout')
 .reverse_depend('//cpython:tapeout')
)
