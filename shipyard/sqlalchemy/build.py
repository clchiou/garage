"""Install SQLAlchemy."""

import shipyard
from foreman import define_rule


(define_rule('sqlalchemy')
 .with_doc(__doc__)
 .with_build(lambda ps: shipyard.python_pip_install(ps, 'SQLAlchemy'))
 .depend('//shipyard/cpython:cpython')
)


(define_rule('build_image')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: shipyard.python_copy_package(
     ps, 'SQLAlchemy', patterns=['*sqlalchemy*']))
 .depend('//shipyard/cpython:build_image')
 .depend('sqlalchemy')
)
