"""Build CPython from source."""

import logging
import re
from collections import namedtuple
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

import shipyard2.rules.bases

LOG = logging.getLogger(__name__)

Version = namedtuple('Version', 'major minor micro')

shipyard2.rules.bases.define_archive(
    url='https://www.python.org/ftp/python/3.10.0/Python-3.10.0.tar.xz',
    checksum='md5:3e7035d272680f80e3ce4e8eb492d580',
)

(foreman.define_parameter.path_typed('prefix')\
 .with_default(Path('/usr/local')))

(foreman.define_parameter.bool_typed('shared')\
 .with_doc('enable building libpython.so (if you are embedding python)')
 .with_default(False))

foreman.define_parameter.list_typed('configuration').with_default([
    '--enable-ipv6',
    '--enable-loadable-sqlite-extensions',
    '--with-computed-gotos',
    '--with-dbmliborder=bdb:gdbm',
    '--with-system-expat',
    '--with-system-ffi',
    '--with-system-libmpdec',
    # Enable optimizations.
    '--enable-optimizations',
    '--with-lto',
])

# This list is derived from running `apt-get build-dep python3.8` on
# Ubuntu 18.04 (note that some packages are not included here).
shipyard2.rules.bases.define_distro_packages([
    # Build tools.
    'autoconf',
    'automake',
    'autotools-dev',
    'binutils',
    'build-essential',
    'cpp',
    'g++',
    'gcc',
    'libtool',
    'm4',
    'make',
    'pkg-config',
    # Libraries.
    'libatomic1',
    'libc6-dev',
    'libmpc3',
    'libmpdec-dev',
    'libmpfr6',
    'libmpx2',
    'libsigsegv2',
    'uuid-dev',
    # Compression.
    'libbz2-dev',
    'liblzma-dev',
    'zlib1g-dev',
    # Console.
    'libncursesw5-dev',
    'libreadline-dev',
    # Database.
    'libdb-dev',
    'libgdbm-dev',
    'libsqlite3-dev',
    # FFI.
    'libffi-dev',
    # Network.
    'libssl-dev',
    # XML.
    'libexpat1-dev',
    'libxml2',  # Do we really need this?
])

(foreman.define_parameter.namedtuple_typed(Version, 'version')\
 .with_doc('cpython version')
 .with_derive(lambda ps: _parse_version(ps['archive'].url)))

(foreman.define_parameter.path_typed('python')\
 .with_doc('path to cpython interpreter')
 .with_derive(lambda ps: _add_version(ps, 'bin/python{}.{}')))

(foreman.define_parameter.path_typed('pip')\
 .with_doc('path to pip')
 .with_derive(lambda ps: _add_version(ps, 'bin/pip{}.{}')))

(foreman.define_parameter.path_typed('modules')\
 .with_doc('path to site-packages directory')
 .with_derive(lambda ps: _add_version(ps, 'lib/python{}.{}')))

foreman.define_parameter.list_typed('unused-modules').with_default([
    'idlelib',
    'lib2to3',
    'tkinter',
    'turtledemo',
    # Remove unit tests.
    'ctypes/test',
    'distutils/tests',
    'sqlite3/test',
    'test',
    'unittest/test',
])


@foreman.rule
@foreman.rule.depend('//bases:build')
@foreman.rule.depend('extract')
@foreman.rule.depend('install')
def build(parameters):
    src_path = (
        parameters['//bases:drydock'] / foreman.get_relpath() /
        parameters['archive'].output
    )
    with scripts.using_cwd(src_path):
        _configure(parameters, src_path)
        _build(parameters, src_path)
        _install(parameters, src_path)
        _fixup(parameters, src_path)


@foreman.rule
@foreman.rule.depend('//bases:build')
@foreman.rule.depend('build')
def trim(parameters):
    LOG.info('remove unused python modules')
    with scripts.using_sudo():
        modules_dir_path = parameters['modules']
        for module in parameters['unused-modules']:
            scripts.rm(modules_dir_path / module, recursive=True)


_VERSION_PATTERN = re.compile(r'/python/(\d+)\.(\d+)\.(\d+)/')


def _parse_version(archive_url):
    match = ASSERT.not_none(_VERSION_PATTERN.search(archive_url))
    return Version(*map(int, match.groups()))


def _add_version(ps, path_template):
    return ps['prefix'] / path_template.format(*ps['version'])


def _configure(parameters, src_path):
    if (src_path / 'Makefile').exists():
        LOG.info('skip: configure cpython build')
        return
    LOG.info('configure cpython build')
    scripts.run([
        './configure',
        *('--prefix', parameters['prefix']),
        *parameters['configuration'],
        *(('--enable-shared', ) if parameters['shared'] else ()),
    ])


def _build(parameters, src_path):
    del parameters  # Unused.
    if (src_path / 'python').exists():
        LOG.info('skip: build cpython')
        return
    LOG.info('build cpython')
    scripts.run(['make'])


def _install(parameters, src_path):
    del src_path  # Unused.
    if parameters['python'].exists():
        LOG.info('skip: install cpython')
        return
    LOG.info('install cpython')
    with scripts.using_sudo():
        # (Probably a bug?) When optimizations are enabled, this will
        # re-run `make run_profile_task`.
        scripts.run(['make', 'install'])
        if parameters['shared']:
            scripts.run(['ldconfig'])


def _fixup(parameters, src_path):
    """Fix up installed paths.

    Custom-built Python sometimes creates pythonX.Ym rather than
    pythonX.Y header directory (same for libpython).
    """
    del src_path  # Unused.
    header_dir_path = _add_version(parameters, 'include/python{}.{}')
    if not header_dir_path.exists():
        alt_header_dir_path = ASSERT.predicate(
            _add_version(parameters, 'include/python{}.{}m'),
            Path.is_dir,
        )
        LOG.info('symlink cpython headers')
        with scripts.using_sudo():
            scripts.ln(alt_header_dir_path.name, header_dir_path)
    libpython_path = _add_version(parameters, 'lib/libpython{}.{}.so')
    if parameters['shared'] and not libpython_path.exists():
        alt_libpython_path = ASSERT.predicate(
            _add_version(parameters, 'lib/libpython{}.{}m.so'),
            Path.is_file,
        )
        LOG.info('symlink cpython library')
        with scripts.using_sudo():
            scripts.ln(alt_libpython_path.name, libpython_path)
