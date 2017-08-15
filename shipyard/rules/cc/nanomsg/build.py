from foreman import get_relpath, rule

from garage import scripts

from templates import common


common.define_git_repo(
    repo='https://github.com/nanomsg/nanomsg.git',
    # A recent commit not far from version 1.0.0
    treeish='b7fd165c20f2fa86192a19e3db2bed46bfadd025',
)


common.define_distro_packages(['cmake', 'gcc', 'pkg-config'])


@rule
@rule.depend('install_packages')
@rule.depend('git_clone')
def build(parameters):
    """Build nanomsg from source."""
    drydock_src = parameters['//base:drydock'] / get_relpath()
    if (drydock_src / 'build/libnanomsg.so').exists():
        return
    scripts.mkdir(drydock_src / 'build')
    with scripts.directory(drydock_src / 'build'):
        scripts.execute('cmake -DCMAKE_INSTALL_PREFIX=/usr/local ..'.split())
        scripts.execute('cmake --build .'.split())
        # Don't run `ctest -C Debug .` at the moment
        with scripts.using_sudo():
            scripts.execute('cmake --build . --target install'.split())
            scripts.execute(['ldconfig'])


@rule
@rule.depend('build')
@rule.reverse_depend('//base:tapeout')
def tapeout(parameters):
    """Copy build artifacts."""
    # Nothing here as //base:tapeout will tapeout /usr/local/lib for us
    pass
