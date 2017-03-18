"""Meta build rules."""

from foreman import define_rule


(define_rule('all')
 .with_doc('Build all packages.')
 .depend('third-party')
)


(define_rule('third-party')
 .with_doc('Build all third-party packages, including all host tools.')
 .depend('//py/cpython:build')
 .depend('//py/lxml:build')
 .depend('//py/mako:build')
 .depend('//py/pyyaml:build')
 .depend('//py/requests:build')
 .depend('//py/sqlalchemy:build')
)
