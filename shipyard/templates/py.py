"""Python build rule templates."""

___all__ = [
    'define_package',
    'define_pip_package',
    'define_source_package',
]

from collections import namedtuple
import logging

from garage import scripts

from foreman import get_relpath, rule

from .common import define_copy_src
from .utils import parse_common_args


LOG = logging.getLogger(__name__)


PackageRules = namedtuple('PackageRules', 'copy_src build unittest tapeout')


@parse_common_args
def define_package(package, *,
                   root: 'root', name: 'name',
                   make_build_cmd=None):
    """Define a first-party Python package, including:
       * [NAME/]copy_src rule
       * [NAME/]build rule
       * [NAME/]unittest rule
       * [NAME/]tapeout rule
    """

    copy_src_rules = define_copy_src(root=root, name=name)

    source_package_rules = define_source_package(
        package, name=name, make_build_cmd=make_build_cmd)

    relpath = get_relpath()

    @rule(name + 'unittest')
    @rule.depend(name + 'build')
    def unittest(parameters):
        drydock_src = parameters['//base:drydock'] / relpath
        scripts.ensure_file(drydock_src / 'setup.py')
        python = parameters['//py/cpython:python']
        with scripts.directory(drydock_src):
            LOG.info('unittest %s', package)
            scripts.execute([
                python, '-m', 'unittest', 'discover',
                # Set start directory to `tests` so that unittest will
                # not try to execute source modules (because some source
                # modules may have missed dependencies and are not
                # importable)
                '--start-directory', 'tests',
                # Without this some imports won't work (why?)
                '--top-level-directory', '.',
            ])

    source_package_rules.build.depend(name + 'copy_src')
    source_package_rules.tapeout.depend(
        name + 'unittest', when=lambda ps: ps['//base:release'])

    return PackageRules(
        copy_src=copy_src_rules.copy_src,
        build=source_package_rules.build,
        unittest=unittest,
        tapeout=source_package_rules.tapeout,
    )


SourcePackageRules = namedtuple('SourcePackageRules', 'build tapeout')


@parse_common_args
def define_source_package(package, *,
                          name: 'name',
                          make_build_cmd=None):
    """Define a Python source package, including:
       * [NAME/]build rule
       * [NAME/]tapeout rule

       You will need to ensure that source code is copied to drydock.
    """

    relpath = get_relpath()

    @rule(name + 'build')
    @rule.depend('//base:build')
    @rule.depend('//py/cpython:build')
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
            with scripts.directory(drydock_src), \
                 scripts.using_sudo(envs=['PYTHONPATH']):
                scripts.execute([python, 'setup.py', 'install'])

    @rule(name + 'tapeout')
    @rule.reverse_depend('//base:tapeout')
    @rule.reverse_depend('//py/cpython:tapeout')
    @rule.depend(name + 'build')
    def tapeout(parameters):
        """Copy Python package build artifacts."""
        _tapeout(parameters, package, ())

    return SourcePackageRules(
        build=build,
        tapeout=tapeout,
    )


PipPackageRules = namedtuple('PipPackageRules', 'build tapeout')


@parse_common_args
def define_pip_package(package, version, *,
                       name: 'name',
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

    return PipPackageRules(
        build=build,
        tapeout=tapeout,
    )


def _tapeout(parameters, package, patterns):
    LOG.info('tapeout %s', package)
    site_packages = parameters['//py/cpython:modules'] / 'site-packages'
    dirs = list(site_packages.glob('%s*' % package))
    for pattern in patterns:
        dirs.extend(site_packages.glob(pattern))
    with scripts.using_sudo():
        scripts.rsync(dirs, parameters['//base:drydock/rootfs'], relative=True)
