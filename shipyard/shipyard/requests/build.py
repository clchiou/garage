"""Install requests."""

import shipyard
from foreman import define_parameter, define_rule


(define_parameter('version')
 .with_doc("""Version to install.""")
 .with_type(str)
 .with_default('2.10.0')
)


(define_rule('build')
 .with_doc(__doc__)
 .with_build(
     lambda ps: shipyard.python_pip_install(ps, 'requests', ps['version']))
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
