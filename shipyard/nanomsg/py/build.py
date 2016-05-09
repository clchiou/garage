"""Build nanomsg Python binding."""

from foreman import define_rule
from shipyard import (
    python_build_package,
    python_copy_package,
)


(define_rule('nanomsg')
 .with_doc(__doc__)
 .with_build(
     lambda ps: python_build_package(ps, 'nanomsg', build_src='nanomsg.py'))
 .depend('//shipyard:shipyard')
 .depend('//shipyard/nanomsg:nanomsg')
 .depend('//shipyard/cpython:cpython')
)


(define_rule('build_image')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: python_copy_package(ps, 'nanomsg'))
 .depend('//shipyard/cpython:build_image')
 .depend('//shipyard/nanomsg:build_image')
 .depend('nanomsg')
)
