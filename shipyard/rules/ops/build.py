"""Build ops-onboard tool.

It is not a containerized app and so its build process is quite
different from other build files.
"""

from foreman import get_relpath, rule

from garage import scripts

from templates import common


# Because distro does not install these by default
common.define_distro_packages([
    'python3-setuptools',
    'zip',
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

    # Use the distro python3 for ops-onboard zipapp, not the python3 we
    # build from source (which is for containers)
    python = '/usr/bin/python3'

    ops_onboard = drydock_src / 'ops-onboard'
    if not ops_onboard.exists():

        # Because zip insists to add '.zip' suffix :(
        ops_onboard_zip = ops_onboard.with_suffix('.zip')

        with scripts.directory(drydock_src / 'py' / 'ops'):
            # Clean up any previous build - just in case
            scripts.rm('build', recursive=True)
            scripts.execute([
                python, 'setup.py', 'build', 'bdist_zipapp', '--output',
                ops_onboard_zip,
            ])

        with scripts.directory(drydock_src / 'py' / 'garage'):
            # Clean up any previous build - just in case
            scripts.rm('build', recursive=True)
            scripts.execute([
                python, 'setup.py', 'build', 'bdist_zipapp', '--output',
                ops_onboard_zip,
            ])

        # startup is not using buildtools (bdist_zipapp) yet
        with scripts.directory(drydock_src / 'py' / 'startup'):
            scripts.execute([
                'zip', '--grow', '-r', ops_onboard_zip, 'startup.py'])

        scripts.mv(ops_onboard_zip, ops_onboard)

    scripts.cp(ops_onboard, parameters['//base:output'] / 'ops-onboard')
