"""Build nanomsg Python binding."""

from foreman import define_rule
from shipyard import (
    python_copy_and_build_package,
    python_copy_package,
)


(define_rule('build')
 .with_doc(__doc__)
 .with_build(lambda ps: \
     python_copy_and_build_package(ps, 'nanomsg', build_src='nanomsg.py'))
 .depend('//base:build')
 .depend('//cpython:build')
 .depend('//nanomsg:build')
)


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: python_copy_package(ps, 'nanomsg'))
 .depend('build')
 .depend('//nanomsg:tapeout')
 .reverse_depend('//base:tapeout')
 .reverse_depend('//cpython:tapeout')
)
