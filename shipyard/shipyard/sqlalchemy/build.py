"""Install SQLAlchemy."""

import shipyard
from foreman import define_rule


(define_rule('build')
 .with_doc(__doc__)
 .with_build(lambda ps: shipyard.python_pip_install(ps, 'SQLAlchemy'))
 .depend('//shipyard/cpython:build')
)


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: shipyard.python_copy_package(
     ps, 'SQLAlchemy', patterns=['*sqlalchemy*']))
 .depend('build')
 .reverse_depend('//shipyard/cpython:final_tapeout')
)