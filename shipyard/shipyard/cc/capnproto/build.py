"""Build capnproto from source."""

from foreman import define_parameter, define_rule, decorate_rule
from shipyard import (
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
     'autoconf',
     'build-essential',
     'libtool',
     'pkg-config',
 ])
)


(define_parameter('repo')
 .with_doc("""Location of source repo.""")
 .with_type(str)
 .with_default('https://github.com/sandstorm-io/capnproto.git')
)
# capnproto hasn't make a release for a while (not because its
# development is stopped but because it's not maintainer's priority).
# So at the moment we would just build from a recent master.
(define_parameter('version')
 .with_doc("""Version to build.""")
 .with_type(str)
 .with_default('2b8cde72a49492d26ac9809b490959b590a3cc7f')
)


@decorate_rule('//base:build')
def build(parameters):
    """Build capnproto from source."""
    build_src = parameters['//base:build'] / 'cc/capnproto'
    git_clone(parameters['repo'], build_src, parameters['version'])
    if not (build_src / 'c++/capnp').is_file():
        install_packages(parameters['deps'])
        # Don't run `make check` at the moment.
        run_commands(path=build_src / 'c++', commands_str='''
            autoreconf -i
            ./configure
            make
            sudo make install
        ''')


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: tapeout_libraries(
     ps, '/usr/local/lib', ['libkj', 'libcapnp']))
 .depend('build')
 .reverse_depend('//base:tapeout')
)
