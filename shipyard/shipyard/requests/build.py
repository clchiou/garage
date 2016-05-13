"""Install requests."""

import shipyard
from foreman import define_rule


(define_rule('build')
 .with_doc(__doc__)
 .with_build(lambda ps: shipyard.python_pip_install(ps, 'requests'))
 .depend('//base:build')
 .depend('//cpython:build')
)


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: shipyard.python_copy_package(ps, 'requests'))
 .depend('build')
 .reverse_depend('//base:tapeout')
 .reverse_depend('//cpython:tapeout')
)
