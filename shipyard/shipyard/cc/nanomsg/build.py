"""Build nanomsg from source."""

from foreman import define_parameter, define_rule, decorate_rule
from shipyard import (
    ensure_directory,
    git_clone,
    install_packages,
    run_commands,
    tapeout_libraries,
)


(define_parameter('deps')
 .with_doc("""Build-time Debian packages.""")
 .with_type(list)
 .with_parse(lambda pkgs: pkgs.split(','))
 .with_default([
     'build-essential',
     'cmake',
 ])
)


(define_parameter('repo')
 .with_doc("""Location of source repo.""")
 .with_type(str)
 .with_default('https://github.com/nanomsg/nanomsg.git')
)
(define_parameter('version')
 .with_doc("""Version to build.""")
 .with_type(str)
 .with_default('1.0.0')
)


@decorate_rule('//base:build')
def build(parameters):
    """Build nanomsg from source."""

    build_src = parameters['//base:build'] / 'cc/nanomsg'
    git_clone(parameters['repo'], build_src, parameters['version'])

    build_dir = build_src / 'build'
    if not ensure_directory(build_dir):
        install_packages(parameters['deps'])
        # Don't run `ctest .` at the moment.
        run_commands(path=build_dir, commands_str='''
            cmake ..
            cmake --build .
            sudo cmake --build . --target install
            sudo ldconfig
        ''')


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(
     lambda ps: tapeout_libraries(ps, '/usr/local/lib', ['libnanomsg']))
 .depend('build')
 .reverse_depend('//base:tapeout')
)
