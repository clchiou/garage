"""Build ops-onboard tool.

It is not a containerized app and so its build process is quite
different from other build files.
"""

from foreman import get_relpath, rule

from garage import scripts

from templates import common


# Because distro does not install these by default.
common.define_distro_packages([
    'python3-setuptools',
])


common.define_copy_src(
    name='garage',
    src_relpath='py/garage',
    dst_relpath='ops/py/garage',
)


common.define_copy_src(
    name='startup',
    src_relpath='py/startup',
    dst_relpath='ops/py/startup',
)


common.define_copy_src(
    name='ops',
    src_relpath='py/ops',
    dst_relpath='ops/py/ops',
)


@rule
@rule.depend('//base:build')
@rule.depend('//host/buildtools:install')
@rule.depend('install_packages')
@rule.depend('garage/copy_src')
@rule.depend('startup/copy_src')
@rule.depend('ops/copy_src')
def package(parameters):
    """Create ops-onboard zipapp."""

    drydock_src = parameters['//base:drydock'] / get_relpath()

    ops_onboard = drydock_src / 'ops-onboard'
    if not ops_onboard.exists():
        for path in ('py/startup', 'py/garage', 'py/ops'):
            with scripts.directory(drydock_src / path):
                # Clean up any previous build - just in case.
                scripts.rm('build', recursive=True)
                scripts.execute([
                    # Use distro's Python interpreter for ops-onboard
                    # zipapp, not the one we build from source (which is
                    # for containers).
                    '/usr/bin/python3',
                    'setup.py', 'build', 'bdist_zipapp',
                    '--output', ops_onboard,
                ])

    scripts.cp(ops_onboard, parameters['//base:output'] / 'ops-onboard')
