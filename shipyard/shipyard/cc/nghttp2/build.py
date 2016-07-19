"""Build nghttp2 from source."""

from foreman import define_parameter, define_rule, decorate_rule
from shipyard import (
    git_clone,
    install_packages,
    run_commands,
    tapeout_libraries,
)


# NOTE: These dependencies are for the executables (e.g., nghttpx).
# libnghttp2.so itself only depends on libc, and thus there is not need
# for a rule to copy libraries.
(define_parameter('deps')
 .with_doc("""Build-time Debian packages.""")
 .with_type(list)
 .with_parse(lambda pkgs: pkgs.split(','))
 .with_default('''
     g++ make binutils autoconf automake autotools-dev libtool pkg-config
     zlib1g-dev libcunit1-dev libssl-dev libxml2-dev libev-dev libevent-dev
     libjansson-dev libjemalloc-dev
 '''.split())
)


(define_parameter('repo')
 .with_doc("""Location of source repo.""")
 .with_type(str)
 .with_default('https://github.com/nghttp2/nghttp2.git')
)
(define_parameter('version')
 .with_doc("""Version to build.""")
 .with_type(str)
 .with_default('v1.11.1')
)


@decorate_rule('//base:build')
def build(parameters):
    """Build nghttp2 from source."""
    build_src = parameters['//base:build'] / 'cc/nghttp2'
    git_clone(parameters['repo'], build_src, parameters['version'])
    if not (build_src / 'src/.libs/nghttp').exists():
        install_packages(parameters['deps'])
        run_commands(path=build_src, commands_str='''
            autoreconf -i
            automake
            autoconf
            ./configure
            make
            sudo make install
        ''')


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(
     lambda ps: tapeout_libraries(ps, '/usr/local/lib', ['libnghttp2']))
 .depend('build')
 .reverse_depend('//base:tapeout')
)
