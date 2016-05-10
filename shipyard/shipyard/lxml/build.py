"""Install lxml."""

import shipyard
from foreman import define_parameter, define_rule


(define_parameter('deps')
 .with_doc("""Build-time Debian packages.""")
 .with_type(list)
 .with_parse(lambda pkgs: pkgs.split(','))
 .with_default([
     'libxml2-dev',
     'libxslt1-dev',
 ])
)
(define_parameter('libs')
 .with_doc("""Runtime library names.""")
 .with_type(list)
 .with_parse(lambda pkgs: pkgs.split(','))
 .with_default([
     'libexslt.so',
     'libicudata.so',
     'libicuuc.so',
     'libstdc++.so',
     'libxml2.so',
     'libxslt.so',
 ])
)


(define_rule('build')
 .with_doc(__doc__)
 .with_build(lambda ps: (
     shipyard.install_packages(ps['deps']),
     shipyard.python_pip_install(ps, 'lxml'),
 ))
 .depend('//shipyard/cpython:build')
)


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: (
     shipyard.copy_libraries(ps, '/usr/lib/x86_64-linux-gnu', ps['libs']),
     shipyard.python_copy_package(ps, 'lxml'),
 ))
 .depend('build')
 .reverse_depend('//shipyard/cpython:final_tapeout')
)
