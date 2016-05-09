"""Install PyYAML."""

import shipyard
from foreman import define_parameter, define_rule


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


(define_rule('pyyaml')
 .with_doc(__doc__)
 .with_build(lambda ps: (
     shipyard.install_packages(ps['deps']),
     shipyard.python_pip_install(ps, 'PyYAML'),
 ))
 .depend('//shipyard:shipyard')
 .depend('//shipyard/cpython:cpython')
)


(define_rule('build_image')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: (
     shipyard.copy_libraries(ps, ps['libs']),
     shipyard.python_copy_package(ps, 'PyYAML', patterns=['*yaml*']),
 ))
 .depend('//shipyard/cpython:build_image')
 .depend('pyyaml')
)