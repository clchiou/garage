"""Build py/garage."""

from foreman import define_rule

import shipyard


(define_rule('garage')
 .with_doc(__doc__)
 .with_build(lambda parameters: shipyard.python_build_package(
     parameters,
     'garage',
     parameters['//shipyard:root'] / 'py/garage',
     parameters['//shipyard:build_src'] / 'garage',
 ))
 .depend('//shipyard/cpython:cpython')
)


(define_rule('build_image')
 .with_doc("""Copy py/garage build artifacts.""")
 .with_build(lambda ps: shipyard.python_copy_package(ps, 'garage'))
 .depend('//shipyard/cpython:build_image')
 .depend('garage')
)
