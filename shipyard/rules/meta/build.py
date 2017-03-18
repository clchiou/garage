"""Meta build rules."""

from foreman import define_rule


(define_rule('all')
 .with_doc('Build all packages.')
 .depend('//py/garage:build')
 .depend('//py/http2:build')
 .depend('//py/nanomsg:build')
 .depend('//py/startup:build')
 .depend('third-party')
)


(define_rule('third-party')
 .with_doc('Build all third-party packages, including all host tools.')
 .depend('//cc/nanomsg:build')
 .depend('//cc/nghttp2:build')
 .depend('//py/cpython:build')
 .depend('//py/curio:build')
 .depend('//py/lxml:build')
 .depend('//py/mako:build')
 .depend('//py/pyyaml:build')
 .depend('//py/requests:build')
 .depend('//py/sqlalchemy:build')
)
