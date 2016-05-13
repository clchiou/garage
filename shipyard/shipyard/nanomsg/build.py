"""Build nanomsg from source."""

from foreman import define_parameter, define_rule, decorate_rule
from shipyard import (

    git_clone,
    run_commands,

    install_packages,

    copy_libraries,
)


(define_parameter('deps')
 .with_doc("""Build-time Debian packages.""")
 .with_type(list)
 .with_parse(lambda pkgs: pkgs.split(','))
 .with_default([
     'autoconf',
     'automake',
     'build-essential',
     'libtool',
 ])
)


# NOTE: Use top of trunk at the moment.
(define_parameter('repo')
 .with_doc("""Location of source repo.""")
 .with_type(str)
 .with_default('https://github.com/nanomsg/nanomsg.git')
)


@decorate_rule('//base:build')
def build(parameters):
    """Build nanomsg from source."""
    install_packages(parameters['deps'])
    build_src = parameters['//base:build_src'] / 'nanomsg'
    git_clone(parameters['repo'], build_src)
    if not (build_src / 'nanocat').exists():
        # Don't run `make check` at the moment.
        run_commands(path=build_src, commands_str='''
            ./autogen.sh
            ./configure
            make
            sudo make install
        ''')


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(
     lambda ps: copy_libraries(ps, '/usr/local/lib', ['libnanomsg']))
 .depend('build')
 .reverse_depend('//base:final_tapeout')
)
