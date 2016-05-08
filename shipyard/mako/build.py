"""Install Mako."""

import shipyard
from foreman import define_rule


(define_rule('mako')
 .with_doc(__doc__)
 .with_build(lambda ps: shipyard.python_pip_install(ps, 'Mako'))
 .depend('//shipyard/cpython:cpython')
)


(define_rule('build_image')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: shipyard.python_copy_package(ps, 'Mako', patterns=[
     '*mako*',
     # Mako's dependency.
     'MarkupSafe',
     '*markupsafe*',
 ]))
 .depend('//shipyard/cpython:build_image')
 .depend('mako')
)
