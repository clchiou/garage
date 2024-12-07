"""Helpers for writing rules for first-party JavaScript packages."""

__all__ = [
    'define_package',
    'find_package',
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


def define_package(
    *,
    name_prefix='',
    deps=(),
    sub_directory_path=None,
):
    """Define a first-party package.

    This defines:
    * Rule: [name_prefix/]build.
    """
    name_prefix = rules.canonicalize_name_prefix(name_prefix)
    rule_build = name_prefix + 'build'

    @foreman.rule(rule_build)
    @foreman.rule.depend(
        '//bases:build',
        when=lambda ps: ps['//bases:inside-builder-pod'] is True,
    )
    @foreman.rule.depend(
        '//third-party/nodejs:build',
        when=lambda ps: ps['//bases:inside-builder-pod'] is True,
    )
    @foreman.rule.depend(
        '//releases:build',
        when=lambda ps: ps['//bases:inside-builder-pod'] is False,
    )
    def build(parameters):
        src_path = find_package(
            parameters,
            foreman.get_relpath(),
            sub_directory_path,
        )
        LOG.info('build first-party package: %s', src_path)
        with scripts.using_cwd(src_path):
            scripts.run(['npm', 'install'])
            scripts.run(['npm', 'run', 'build'])

    for dep in deps:
        build = build.depend(dep)

    return PackageRules(build=build)


def find_package(parameters, relpath, sub_directory_path=None):
    """Find path to a first-party package."""
    root_paths = parameters['//bases:roots']
    for root_path in root_paths:
        path = root_path / relpath
        if sub_directory_path:
            path /= sub_directory_path
        if (path / 'package.json').is_file():
            return path
    return ASSERT.unreachable(
        'cannot find package {} under: {}', relpath, root_paths
    )
