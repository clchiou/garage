from foreman import get_relpath, rule

from garage import scripts

from templates import common


common.define_git_repo(
    repo='https://github.com/capnproto/capnproto.git',
    treeish='v0.6.1',
)


common.define_distro_packages([
    'autoconf',
    'automake',
    'g++',
    'libtool',
    'pkg-config',
])


@rule
@rule.depend('install_packages')
@rule.depend('git_clone')
def build(parameters):
    """Build capnproto from source."""
    drydock_src = parameters['//base:drydock'] / get_relpath()
    if (drydock_src / 'c++/.libs/libcapnp.so').exists():
        return
    with scripts.directory(drydock_src / 'c++'):
        scripts.execute(['autoreconf', '-i'])
        scripts.execute(['./configure'])
        # Don't run `make check` at the moment.
        scripts.execute(['make'])
        with scripts.using_sudo():
            scripts.execute(['make', 'install'])
            scripts.execute(['ldconfig'])


@rule
@rule.depend('build')
@rule.reverse_depend('//base:tapeout')
def tapeout(parameters):
    """Copy build artifacts."""
    # Nothing here as //base:tapeout will tapeout /usr/local/lib for us.
    pass
