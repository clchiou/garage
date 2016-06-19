"""Install Mako under host-only venv."""

from pathlib import Path

from foreman import define_parameter, define_rule
from shipyard import call


(define_rule('install')
 .with_doc(__doc__)
 .with_build(
     lambda ps: call([str(ps['//host/cpython:pip']), 'install', 'Mako']))
 .depend('//host/cpython:install')
)
