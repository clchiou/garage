"""Build nanomsg Python binding."""

from foreman import define_rule
from shipyard import (
    python_build_package,
    python_copy_package,
)


(define_rule('build')
 .with_doc(__doc__)
 .with_build(
     lambda ps: python_build_package(ps, 'nanomsg', build_src='nanomsg.py'))
 .depend('//shipyard/cpython:build')
 .depend('//shipyard/nanomsg:build')
)


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: python_copy_package(ps, 'nanomsg'))
 .depend('build')
 .depend('//shipyard/nanomsg:tapeout')
 .reverse_depend('//shipyard/cpython:final_tapeout')
)
