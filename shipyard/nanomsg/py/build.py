"""Build nanomsg Python binding."""

import shipyard
from foreman import define_rule


(define_rule('nanomsg')
 .with_doc(__doc__)
 .with_build(lambda parameters: shipyard.python_build_package(
     parameters,
     'nanomsg',
     parameters['//shipyard:root'] / 'py/nanomsg',
     parameters['//shipyard:build_src'] / 'nanomsg.py',
 ))
 .depend('//shipyard/cpython:cpython')
)


(define_rule('build_image')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: shipyard.python_copy_package(ps, 'nanomsg'))
 .depend('//shipyard/cpython:build_image')
 .depend('//shipyard/nanomsg:build_image')
 .depend('nanomsg')
)
