"""Install requests."""

import shipyard
from foreman import define_rule


(define_rule('requests')
 .with_doc(__doc__)
 .with_build(lambda ps: shipyard.python_pip_install(ps, 'requests'))
 .depend('//shipyard/cpython:cpython')
)


(define_rule('build_image')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: shipyard.python_copy_package(ps, 'requests'))
 .depend('//shipyard/cpython:build_image')
 .depend('requests')
)
