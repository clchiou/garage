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


@decorate_rule
def nanomsg(parameters):
    """Build nanomsg from source."""
    install_packages(parameters['deps'])
    src_path = parameters['//shipyard:build_src'] / 'nanomsg'
    git_clone(parameters['repo'], src_path)
    if not (src_path / 'nanocat').exists():
        # Don't run `make check` at the moment.
        run_commands(path=src_path, commands_str='''
            ./autogen.sh
            ./configure
            make
            sudo make install
        ''')


(define_rule('build_image')
 .with_doc("""Copy build artifacts.""")
 .with_build(
     lambda ps: copy_libraries(ps, ['libnanomsg'], lib_dir='/usr/local/lib'))
 .depend('nanomsg')
)
