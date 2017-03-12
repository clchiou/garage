"""Python build rule templates."""

___all__ = [
    'define_package',
    'define_pip_package',
]

import logging

from garage import scripts

from foreman import get_relpath, rule

from .common import define_package_common
from .utils import parse_common_args


LOG = logging.getLogger(__name__)


@parse_common_args
def define_package(package, *,
                   root: 'root', name: 'name',
                   build_deps=(),
                   tapeout_deps=(),
                   make_build_cmd=None):
    """Define a first-party Python package, including:
       * [NAME/]copy_src rule
       * [NAME/]build rule
       * [NAME/]tapeout rule
    """

    define_package_common(root=root, name=name)

    relpath = get_relpath()

    @rule(name + 'build')
    @rule.depend('//base:build')
    @rule.depend('//py/cpython:build')
    @rule.depend(name + 'copy_src')
    def build(parameters):
        """Build Python package."""

        drydock_src = parameters['//base:drydock'] / relpath
        scripts.ensure_file(drydock_src / 'setup.py')

        # Retrieve the Python interpreter
        python = parameters['//py/cpython:python']

        # Run `python setup.py build`
        if not (drydock_src / 'build').exists():
            LOG.info('build %s', package)
            cmd = [python, 'setup.py']
            if make_build_cmd:
                cmd.extend(make_build_cmd(parameters))
            else:
                cmd.append('build')
            with scripts.directory(drydock_src):
                scripts.execute(cmd)

        # Run `sudo python setup.py install`
        site_packages = parameters['//py/cpython:modules'] / 'site-packages'
        if not list(site_packages.glob('%s*' % package)):
            LOG.info('install %s', package)
            # sudo does not preserve PYTHONPATH even with '--preserve-env'.
            # Run `sudo sudo -V` for the list of preserved variables.
            with scripts.using_sudo(envs=['PYTHONPATH']):
                scripts.execute([python, 'setup.py', 'install'])

    for dep in build_deps:
        build.depend(dep)

    @rule(name + 'tapeout')
    @rule.reverse_depend('//base:tapeout')
    @rule.reverse_depend('//py/cpython:tapeout')
    @rule.depend(name + 'build')
    def tapeout(parameters):
        """Copy Python package build artifacts."""
        _tapeout(parameters, package, ())

    for dep in tapeout_deps:
        tapeout.depend(dep)

    return (build, tapeout)


@parse_common_args
def define_pip_package(package, version, *,
                       name: 'name',
                       distro_packages=(),
                       patterns=()):
    """Define a third-party Python package, including:
       * [NAME/]build rule
       * [NAME/]tapeout rule
    """

    @rule(name + 'build')
    @rule.depend('//base:build')
    @rule.depend('//py/cpython:build')
    def build(parameters):
        """Install Python package through pip."""
        LOG.info('install %s version %s', package, version)
        site_packages = parameters['//py/cpython:modules'] / 'site-packages'
        if not list(site_packages.glob('%s*' % package)):
            with scripts.using_sudo():
                scripts.apt_get_install(distro_packages)
                scripts.execute([
                    parameters['//py/cpython:pip'], 'install',
                    '%s==%s' % (package, version),
                ])

    @rule(name + 'tapeout')
    @rule.reverse_depend('//base:tapeout')
    @rule.reverse_depend('//py/cpython:tapeout')
    @rule.depend(name + 'build')
    def tapeout(parameters):
        """Copy Python package artifacts."""
        _tapeout(parameters, package, patterns)

    return (build, tapeout)


def _tapeout(parameters, package, patterns):
    LOG.info('tapeout %s', package)
    site_packages = parameters['//py/cpython:modules'] / 'site-packages'
    dirs = list(site_packages.glob('%s*' % package))
    for pattern in patterns:
        dirs.extend(site_packages.glob(pattern))
    with scripts.using_sudo():
        scripts.rsync(dirs, parameters['//base:drydock/rootfs'], relative=True)