"""Install Mako under host-only venv."""

from foreman import define_rule
from shipyard import execute


(define_rule('install')
 .with_doc(__doc__)
 .with_build(
     lambda ps: execute([ps['//host/cpython:pip'], 'install', 'Mako']))
 .depend('//host/cpython:install')
)
