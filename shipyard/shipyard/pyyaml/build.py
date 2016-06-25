"""Install PyYAML."""

import shipyard
from foreman import define_parameter, define_rule


(define_parameter('version')
 .with_doc("""Version to install.""")
 .with_type(str)
 .with_default('3.11')
)


(define_parameter('deps')
 .with_doc("""Build-time Debian packages.""")
 .with_type(list)
 .with_parse(lambda pkgs: pkgs.split(','))
 .with_default([
     'libyaml-dev',
 ])
)
(define_parameter('libs')
 .with_doc("""Runtime library names.""")
 .with_type(list)
 .with_parse(lambda pkgs: pkgs.split(','))
 .with_default([
     'libyaml',  # Match both libyaml-0.so and libyaml.so.
 ])
)


(define_rule('build')
 .with_doc(__doc__)
 .with_build(lambda ps: shipyard.python_pip_install(
     ps, 'PyYAML', version=ps['version'], deps=ps['deps']))
 .depend('//base:build')
 .depend('//cpython:build')
)


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: (
     shipyard.copy_libraries(ps, '/usr/lib/x86_64-linux-gnu', ps['libs']),
     shipyard.python_copy_package(ps, 'PyYAML', patterns=['*yaml*']),
 ))
 .depend('build')
 .reverse_depend('//base:tapeout')
 .reverse_depend('//cpython:tapeout')
)
