"""Build garage."""

import shipyard
from foreman import define_rule


(define_rule('garage')
 .with_doc(__doc__)
 .with_build(lambda ps: shipyard.python_build_package(ps, 'garage'))
 .depend('//shipyard:shipyard')
 .depend('//shipyard/cpython:cpython')
)


(define_rule('build_image')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: shipyard.python_copy_package(ps, 'garage'))
 .depend('//shipyard/cpython:build_image')
 .depend('garage')
)
