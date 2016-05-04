"""Build CPython from source."""

import itertools
import logging
from collections import namedtuple
from pathlib import Path

from foreman import define_parameter, decorate_rule

from shipyard import (
    call,
    ensure_directory,
    sync_files,
    tar_extract,
    wget,
)


LOG = logging.getLogger(__name__)


(define_parameter('prefix')
 .with_type(Path)
 .with_default(Path('/usr/local'))
)


(define_parameter('deps')
 .with_doc("""Build-time Debian packages.""")
 .with_type(list)
 .with_parse(lambda pkgs: pkgs.split(','))
 .with_default([
     'build-essential',
     # Compression...
     'libbz2-dev',
     'liblzma-dev',
     'zlib1g-dev',
     # Console...
     'libncursesw5-dev',
     'libreadline-dev',
     # Database...
     'libdb-dev',
     'libgdbm-dev',
     'libsqlite3-dev',
     # Network...
     'libssl-dev',
 ])
)


TarballInfo = namedtuple('TarballInfo', 'uri filename output')
(define_parameter('tarball')
 .with_doc("""Python source tarball.""")
 .with_type(TarballInfo)
 .with_parse(lambda info: TarballInfo(*info.split(',')))
 .with_default(TarballInfo(
     uri='https://www.python.org/ftp/python/3.5.1/Python-3.5.1.tar.xz',
     filename='Python-3.5.1.tar.xz',
     output='Python-3.5.1',
 ))
)


Version = namedtuple('Version', 'major minor')
(define_parameter('version')
 .with_doc("""Python version.""")
 .with_type(Version)
 .with_parse(lambda version: Version(*map(int, version.split('.'))))
 .with_default(Version(3, 5))
)


@decorate_rule('install_deps', 'download')
def cpython(parameters):
    """Build CPython from source."""

    src_path = get_src_path(parameters)

    if not (src_path / 'Makefile').exists():
        LOG.info('configure cpython')
        cmd = ['./configure', '--prefix', parameters['prefix']]
        call(cmd, cwd=str(src_path))

    if not (src_path / 'python').exists():
        LOG.info('build cpython')
        call(['make'], cwd=str(src_path))
        LOG.info('install cpython')
        call(['sudo', 'make', 'install'], cwd=str(src_path))


@decorate_rule
def install_deps(parameters):
    """Install build dependencies."""
    LOG.info('install packages')
    call(['sudo', 'apt-get', 'install', '--yes'] + parameters['deps'])


@decorate_rule
def download(parameters):
    """Download source repo."""

    root_path = get_root_path(parameters)
    ensure_directory(root_path)
    tarball_path = root_path / parameters['tarball'].filename

    if not tarball_path.exists():
        LOG.info('download tarball')
        wget(parameters['tarball'].uri, tarball_path)

    if not get_src_path(parameters).exists():
        LOG.info('extract tarball')
        tar_extract(tarball_path, root_path)


@decorate_rule('cpython', '//shipyard:build_image')
def build_image(parameters):
    """Copy final CPython build artifacts."""

    LOG.info('copy cpython runtime libraries')
    lib_dir = Path('/usr/lib/x86_64-linux-gnu')
    libs = list(itertools.chain(
        lib_dir.glob('libgdbm.so*'),
        lib_dir.glob('libgdbm_compat.so*'),
        lib_dir.glob('libpanelw.so*'),
        lib_dir.glob('libsqlite3.so*'),
    ))
    sync_files(libs, parameters['//shipyard:build_rootfs'], sudo=True)

    LOG.info('copy cpython modules')
    lib_dir = get_lib_dir(parameters)
    excludes = [
        # Exclude idlelib, lib2to3, tkinter, and turtledemo.
        lib_dir / 'idlelib',
        lib_dir / 'lib2to3',
        lib_dir / 'tkinter',
        lib_dir / 'turtledemo',
        # Exclude tests.
        lib_dir / 'ctypes/test',
        lib_dir / 'distutils/tests',
        lib_dir / 'sqlite3/test',
        lib_dir / 'test',
        lib_dir / 'unittest/test',
        # Exclude site-packages (you will have to cherry-pick them).
        lib_dir / 'site-packages',
    ]
    sync_files([lib_dir], parameters['//shipyard:build_rootfs'],
               excludes=excludes, sudo=True)

    LOG.info('copy cpython binaries')
    bins = list(get_bin_dir(parameters)
                .glob('python%d*' % parameters['version'].major))
    sync_files(bins, parameters['//shipyard:build_rootfs'], sudo=True)


def get_root_path(parameters):
    return parameters['//shipyard:build_src'] / 'cpython'


def get_src_path(parameters):
    return get_root_path(parameters) / parameters['tarball'].output


def get_bin_dir(parameters):
    return parameters['prefix'] / 'bin'


def get_lib_dir(parameters):
    return parameters['prefix'] / ('lib/python%d.%d' % parameters['version'])
