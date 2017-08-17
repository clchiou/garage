"""Build capnpc-java (runtime library is installed through Maven)."""

from pathlib import Path

from foreman import get_relpath, rule

from garage import scripts

from templates import common


common.define_git_repo(
    repo='https://github.com/capnproto/capnproto-java.git',
    treeish='v0.1.2',
)


common.define_distro_packages(['g++', 'pkg-config'])


@rule
@rule.depend('//cc/capnproto:build')
@rule.depend('install_packages')
@rule.depend('git_clone')
def install(parameters):
    """Build capnpc-java from source."""

    drydock_src = parameters['//base:drydock'] / get_relpath()
    if (drydock_src / 'capnpc-java').exists():
        return

    def get_var_path(name):
        cmd = ['pkg-config', '--variable=%s' % name, 'capnp']
        path = scripts.execute(cmd, capture_stdout=True).stdout
        path = Path(path.decode('utf8').strip())
        return scripts.ensure_directory(path)

    with scripts.directory(drydock_src):
        scripts.execute(['make'])
        with scripts.using_sudo():
            scripts.cp(
                'capnpc-java',
                get_var_path('exec_prefix') / 'bin',
            )
            scripts.cp(
                'compiler/src/main/schema/capnp/java.capnp',
                get_var_path('includedir') / 'capnp',
            )
