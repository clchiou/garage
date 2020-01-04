"""Helpers for writing rules that depends on //third-party/cpython."""

__all__ = [
    'define_host_package',
    'define_package',
    'define_pypi_package',
]

import dataclasses
import logging

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

from shipyard2 import rules

LOG = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class PackageRules:
    build: foreman.Rule


def define_host_package(
    *,
    name_prefix='',
):
    """Define a first-party host package.

    This defines:
    * Rule: [name_prefix/]build.
    """
    name_prefix = rules.canonicalize_name_prefix(name_prefix)
    rule_build = name_prefix + 'build'

    @foreman.rule(rule_build)
    @foreman.rule.depend('//bases:build')
    @foreman.rule.depend('//third-party/cpython:build')
    def build(parameters):
        src_path = _find_src_path(parameters)
        LOG.info('export first-party host package: %s', src_path)
        scripts.export_path('PYTHONPATH', src_path)

    return PackageRules(build=build)


def define_package(
    *,
    name_prefix='',
    parameter_extra_commands=None,
):
    """Define a first-party package.

    This defines:
    * Rule: [name_prefix/]build.
    """
    name_prefix = rules.canonicalize_name_prefix(name_prefix)
    rule_build = name_prefix + 'build'

    @foreman.rule(rule_build)
    @foreman.rule.depend('//bases:build')
    @foreman.rule.depend('//third-party/cpython:build')
    def build(parameters):
        src_path = _find_src_path(parameters)
        LOG.info('build first-party package: %s', src_path)
        with scripts.using_cwd(src_path):
            _build(parameters, parameter_extra_commands)

    return PackageRules(build=build)


def _find_src_path(parameters):
    relpath = foreman.get_relpath()
    for root_path in parameters['//bases:roots']:
        path = root_path / relpath
        if (path / 'setup.py').is_file():
            return path
    return ASSERT.unreachable('cannot find package under: {}', relpath)


def _build(parameters, parameter_extra_commands):
    # `sudo --preserve-env` does not preserve PYTHONPATH (in case you
    # are curious, you may run `sudo sudo -V` to get the list of
    # preserved variables).
    with scripts.using_sudo(), scripts.preserving_sudo_envs(['PYTHONPATH']):
        scripts.run([
            parameters['//third-party/cpython:pip'],
            'install',
            # Use `--no-deps` (`python3 setup.py install` does not
            # support this, by the way) so that we won't implicitly
            # install dependencies (you must explicitly specify them).
            '--no-deps',
            # Because we add a few Python package to PYTHONPATH, such as
            # g1.bases, we need to force their installation (otherwise
            # pip would consider them already installed).
            '--upgrade',
            '--force-reinstall',
            *_build_get_extra_commands(parameters, parameter_extra_commands),
            '.',
        ])


def _build_get_extra_commands(parameters, parameter_extra_commands):
    if parameter_extra_commands is None:
        return
    for command in parameters[parameter_extra_commands]:
        yield '--global-option=%s' % command


def define_pypi_package(
    package,
    version,
    *,
    name_prefix='',
):
    """Define a PyPI-hosted package.

    This defines:
    * Rule: [name_prefix/]build.
    """
    name_prefix = rules.canonicalize_name_prefix(name_prefix)
    rule_build = name_prefix + 'build'

    @foreman.rule(rule_build)
    @foreman.rule.depend('//bases:build')
    @foreman.rule.depend('//third-party/cpython:build')
    def build(parameters):
        LOG.info('install package %s version %s', package, version)
        with scripts.using_sudo():
            scripts.run([
                parameters['//third-party/cpython:pip'],
                'install',
                '%s==%s' % (package, version),
            ])

    return PackageRules(build=build)
