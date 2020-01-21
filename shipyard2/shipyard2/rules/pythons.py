"""Helpers for writing rules that depends on //third-party/cpython."""

__all__ = [
    'define_build_time_package',
    'define_package',
    'define_pypi_package',
    'find_package',
]

import dataclasses
import logging
import typing

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

from shipyard2 import rules

LOG = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class PackageRules:
    build: foreman.Rule
    build_extras: typing.Mapping[str, foreman.Rule]


def define_build_time_package(
    *,
    name_prefix='',
):
    """Define a first-party build-time package.

    This defines:
    * Rule: [name_prefix/]build.
    """
    name_prefix = rules.canonicalize_name_prefix(name_prefix)
    rule_build = name_prefix + 'build'

    @foreman.rule(rule_build)
    @foreman.rule.depend('//bases:build')
    @foreman.rule.depend('//third-party/cpython:build')
    def build(parameters):
        src_path = find_package(parameters, foreman.get_relpath())
        LOG.info('export first-party host package: %s', src_path)
        scripts.export_path('PYTHONPATH', src_path)

    return PackageRules(build=build, build_extras={})


def define_package(
    *,
    name_prefix='',
    build_time_deps=(),
    deps=(),
    extras=(),
    make_global_options=None,
):
    """Define a first-party package.

    This defines:
    * Rule: [name_prefix/]build.
    * Rule: [name_prefix/]build/<extra> for each extra.
    """
    name_prefix = rules.canonicalize_name_prefix(name_prefix)
    rule_build = name_prefix + 'build'

    @foreman.rule(rule_build)
    @foreman.rule.depend('//bases:build')
    @foreman.rule.depend('//third-party/cpython:build')
    def build(parameters):
        src_path = find_package(parameters, foreman.get_relpath())
        LOG.info('build first-party package: %s', src_path)
        with scripts.using_cwd(src_path):
            _build(parameters, make_global_options)

    for build_time_dep in build_time_deps:
        build = build.depend(build_time_dep)
    for dep in deps:
        build = build.depend(dep)

    build_extras = {
        extra: _make_build_extra(extra, rule_build, extra_deps)
        for extra, extra_deps in extras
    }

    return PackageRules(build=build, build_extras=build_extras)


def find_package(parameters, relpath):
    """Find path to a first-party package."""
    root_paths = parameters['//bases:roots']
    for root_path in root_paths:
        path = root_path / relpath
        if (path / 'setup.py').is_file():
            return path
    return ASSERT.unreachable(
        'cannot find package {} under: {}', relpath, root_paths
    )


def _make_build_extra(extra, rule_build, deps):
    rule = foreman.define_rule('%s/%s' % (rule_build, extra))
    rule = rule.depend(rule_build)
    for dep in deps:
        rule = rule.depend(dep)
    return rule


def _build(parameters, make_global_options):
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
            *_build_get_global_options(parameters, make_global_options),
            '.',
        ])


def _build_get_global_options(parameters, make_global_options):
    if make_global_options is None:
        return
    for opt in make_global_options(parameters):
        yield '--global-option=%s' % opt


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

    return PackageRules(build=build, build_extras={})
