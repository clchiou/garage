"""Helpers and templates for building Python packages."""

__all__ = [
    # Helpers
    'build_package',
    'pip_install',
    'tapeout_package',
    'make_manifest',
    # Templates
    'define_package',
    'define_pip_package',
]

import itertools
import logging

from foreman import define_parameter, define_rule

from . import (
    combine_dicts,
    copy_source,
    define_package_common,
    ensure_file,
    execute,
    install_packages,
    rsync,
    tapeout_libraries,
)


LOG = logging.getLogger(__name__)


### Helpers


def build_package(parameters, package_name, build_src, *, build_cmd=None):
    LOG.info('build %s', package_name)
    python = parameters['//py/cpython:python']
    if not (build_src / 'build').exists():
        cmd = [python, 'setup.py']
        if build_cmd:
            cmd.extend(build_cmd)
        else:
            cmd.append('build')
        execute(cmd, cwd=build_src)
    site_packages = parameters['//py/cpython:modules'] / 'site-packages'
    if not list(site_packages.glob('%s*' % package_name)):
        execute(['sudo', python, 'setup.py', 'install'], cwd=build_src)


def pip_install(parameters, package_name, *, version=None, deps=None):
    LOG.info('install %s with version %s', package_name, version)
    site_packages = parameters['//py/cpython:modules'] / 'site-packages'
    if not list(site_packages.glob('%s*' % package_name)):
        if deps:
            install_packages(deps)
        if version:
            target = '%s==%s' % (package_name, version)
        else:
            target = package_name
        execute(['sudo', parameters['//py/cpython:pip'], 'install', target])


def tapeout_package(parameters, package_name, patterns=()):
    LOG.info('tapeout %s', package_name)
    site_packages = parameters['//py/cpython:modules'] / 'site-packages'
    dirs = list(site_packages.glob('%s*' % package_name))
    dirs.extend(itertools.chain.from_iterable(
        map(site_packages.glob, patterns)))
    rsync(dirs, parameters['//base:rootfs'], relative=True, sudo=True)


def make_manifest(_, base_manifest):
    return combine_dicts(
        base_manifest,
        {
            'app': {
                'exec': [
                    '/usr/local/bin/python3',
                ],
                'user': 'nobody',
                'group': 'nogroup',
                'environment': [
                    {
                        'name': 'LD_LIBRARY_PATH',
                        'value': '/usr/local/lib',
                    },
                    {
                        'name': 'PYTHONIOENCODING',
                        'value': 'UTF-8',
                    }
                ],
                'workingDirectory': '/',
            },
        },
    )


### Templates


def define_package(
        *,
        package_name,
        derive_src_path,
        derive_build_src_path,
        build_rule_deps=(),
        tapeout_rule_deps=()):

    define_package_common(
        derive_src_path=derive_src_path,
        derive_build_src_path=derive_build_src_path,
    )

    build_rule = (
        define_rule('build')
        .with_doc("""Build Python package.""")
        .with_build(lambda ps: (
            copy_source(ps['src'], ps['build_src']),
            ensure_file(ps['build_src'] / 'setup.py'),
            build_package(ps, package_name, ps['build_src']),
        ))
        .depend('//base:build')
        .depend('//py/cpython:build')
    )
    for rule in build_rule_deps:
        build_rule.depend(rule)

    tapeout_rule = (
        define_rule('tapeout')
        .with_doc("""Copy Python package build artifacts.""")
        .with_build(lambda ps: tapeout_package(ps, package_name))
        .depend('build')
        .reverse_depend('//base:tapeout')
        .reverse_depend('//py/cpython:tapeout')
    )
    for rule in tapeout_rule_deps:
        tapeout_rule.depend(rule)


def define_pip_package(
        *,
        package_name,
        version,
        dep_pkgs=None,
        dep_libs=None,
        patterns=()):

    (
        define_parameter('version')
        .with_doc("""Version to install.""")
        .with_type(str)
        .with_default(version)
    )

    (
        define_parameter('deps')
        .with_doc("""Build-time Debian packages.""")
        .with_type(list)
        .with_parse(lambda pkgs: pkgs.split(','))
        .with_default(dep_pkgs or [])
    )
    (
        define_parameter('libs')
        .with_doc("""Runtime library names.""")
        .with_type(list)
        .with_parse(lambda libs: libs.split(','))
        .with_default(dep_libs or [])
    )

    (
        define_rule('build')
        .with_doc("""Install Python package.""")
        .with_build(lambda ps: pip_install(
            ps, package_name, version=ps['version'], deps=ps['deps']))
        .depend('//base:build')
        .depend('//py/cpython:build')
    )

    def tapeout(parameters):
        if parameters['libs']:
            tapeout_libraries(
                parameters, '/usr/lib/x86_64-linux-gnu', parameters['libs'])
        tapeout_package(parameters, package_name, patterns=patterns)

    (
        define_rule('tapeout')
        .with_doc("""Copy Python package artifacts.""")
        .with_build(tapeout)
        .depend('build')
        .reverse_depend('//base:tapeout')
        .reverse_depend('//py/cpython:tapeout')
    )
