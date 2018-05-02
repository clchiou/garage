from foreman import get_relpath, rule

from garage import scripts

from templates import common


common.define_git_repo(
    repo='https://github.com/nghttp2/nghttp2.git',
    treeish='v1.31.1',
)


# Most of these dependencies are for the executables (e.g., nghttpx).
# libnghttp2.so itself only depends on libc.
common.define_distro_packages('''
    g++ make binutils autoconf automake autotools-dev libtool pkg-config
    zlib1g-dev libcunit1-dev libssl-dev libxml2-dev libev-dev libevent-dev
    libjansson-dev libc-ares-dev libjemalloc-dev libsystemd-dev libspdylay-dev
'''.split())


@rule
@rule.depend('install_packages')
@rule.depend('git_clone')
def build(parameters):
    """Build nghttp2 from source."""
    drydock_src = parameters['//base:drydock'] / get_relpath()
    if (drydock_src / 'lib/.libs/libnghttp2.so').exists():
        return
    with scripts.directory(drydock_src):
        cmds = [
            'autoreconf -i',
            'automake',
            'autoconf',
            './configure',
            'make',
        ]
        for cmd in cmds:
            scripts.execute(cmd.split())
        with scripts.using_sudo():
            scripts.execute(['make', 'install'])
            scripts.execute(['ldconfig'])


@rule
@rule.depend('build')
@rule.reverse_depend('//base:tapeout')
def tapeout(parameters):
    """Copy build artifacts."""
    # Nothing here as //base:tapeout will tapeout /usr/local/lib for us
    pass
