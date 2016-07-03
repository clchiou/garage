"""Helpers and templates for building JavaScript packages."""

__all__ = [
    # Helpers
    'npm_install',
    'npm_link',
    # Templates
    'define_npm_package',
]

import logging

from foreman import define_rule

from . import (
    copy_source,
    define_package_common,
    ensure_file,
    execute,
)


LOG = logging.getLogger(__name__)


### Helpers


def npm_install(pkg_path, deps):
    LOG.info('install npm package: %s', pkg_path)
    _npm_link_dependencies(pkg_path, deps)
    execute(['npm', 'install'], cwd=pkg_path)


def npm_link(pkg_path, deps):
    LOG.info('link npm package: %s', pkg_path)
    _npm_link_dependencies(pkg_path, deps)
    execute(['npm', 'link'], cwd=pkg_path)


def _npm_link_dependencies(pkg_path, deps):
    for dep in deps:
        execute(['npm', 'link', dep], cwd=pkg_path)


### Templates


def define_npm_package(
        *,
        derive_src_path,
        derive_build_src_path,
        dep_rules=(),
        dep_pkgs=()):
    """Define an npm-managed JavaScript package."""

    define_package_common(
        derive_src_path=derive_src_path,
        derive_build_src_path=derive_build_src_path,
    )

    rule = (
        define_rule('build')
        .with_doc("""Link to an npm-managed JavaScript package.""")
        .with_build(lambda ps: (
            copy_source(ps['src'], ps['build_src']),
            ensure_file(ps['build_src'] / 'package.json'),
            npm_link(ps['build_src'], deps=dep_pkgs),
        ))
        .depend('//base:build')
        .depend('//host/node:install')
    )
    for dep_rule in dep_rules:
        rule.depend(dep_rule)
