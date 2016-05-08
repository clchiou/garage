"""Build startup."""

from pathlib import Path

import shipyard
from foreman import define_parameter, define_rule
from shipyard import get_home


(define_parameter('src')
 .with_doc("""Location of the startup source repo.""")
 .with_type(Path)
 .with_default(get_home() / 'startup')
)


(define_rule('startup')
 .with_doc(__doc__)
 .with_build(lambda parameters: shipyard.python_build_package(
     parameters,
     'startup',
     parameters['//shipyard/startup:src'],
     parameters['//shipyard:build_src'] / 'startup',
 ))
 .depend('//shipyard/cpython:cpython')
)


(define_rule('build_image')
 .with_doc("""Copy startup build artifacts.""")
 .with_build(lambda ps: shipyard.python_copy_package(ps, 'startup'))
 .depend('//shipyard/cpython:build_image')
 .depend('startup')
)
