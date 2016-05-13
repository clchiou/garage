"""Build CPython from source."""

import logging
from collections import namedtuple
from pathlib import Path

from foreman import define_parameter, define_rule, decorate_rule
from shipyard import (

    call,
    ensure_directory,
    rsync,
    tar_extract,
    wget,

    install_packages,

    copy_libraries,
)


LOG = logging.getLogger(__name__)


(define_parameter('prefix')
 .with_type(Path)
 .with_default(Path('/usr/local'))
)
(define_parameter('python')
 .with_type(Path)
 .with_derive(lambda ps: ps['prefix'] / ('bin/python%d.%d' % ps['version']))
)
(define_parameter('pip')
 .with_type(Path)
 .with_derive(lambda ps: ps['prefix'] / ('bin/pip%d.%d' % ps['version']))
)
(define_parameter('modules')
 .with_type(Path)
 .with_derive(lambda ps: ps['prefix'] / ('lib/python%d.%d' % ps['version']))
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
(define_parameter('libs')
 .with_doc("""Runtime libraries.""")
 .with_type(list)
 .with_parse(lambda pkgs: pkgs.split(','))
 .with_default([
     'libgdbm.so',
     'libgdbm_compat.so',
     'libpanelw.so',
     'libsqlite3.so',
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


(define_parameter('build_src')
 .with_type(Path)
 .with_derive(lambda ps: \
     ps['//base:build_src'] / 'cpython' / ps['tarball'].output)
)


@decorate_rule('//base:build',
               'install_deps',
               'download')
def build(parameters):
    """Build CPython from source."""

    src_path = parameters['build_src']

    if not (src_path / 'Makefile').exists():
        LOG.info('configure cpython')
        cmd = ['./configure', '--prefix', str(parameters['prefix'])]
        call(cmd, cwd=str(src_path))

    if not (src_path / 'python').exists():
        LOG.info('build cpython')
        call(['make'], cwd=str(src_path))
        LOG.info('install cpython')
        call(['sudo', 'make', 'install'], cwd=str(src_path))


(define_rule('install_deps')
 .with_doc("""Install build dependencies.""")
 .with_build(lambda ps: install_packages(ps['deps']))
)


@decorate_rule
def download(parameters):
    """Download source repo."""

    build_src = parameters['build_src']

    ensure_directory(build_src.parent)

    tarball_path = build_src.parent / parameters['tarball'].filename
    if not tarball_path.exists():
        LOG.info('download tarball')
        wget(parameters['tarball'].uri, tarball_path)

    if not build_src.exists():
        LOG.info('extract tarball')
        tar_extract(tarball_path, build_src.parent)


# NOTE: All Python module's `tapeout` rules should reverse depend on
# this rule rather than `//base:final_tapeout` directly.
def final_tapeout(parameters):
    """Join point of all Python module's `tapeout` rule."""

    LOG.info('copy cpython runtime libraries')
    copy_libraries(parameters, '/usr/lib/x86_64-linux-gnu', parameters['libs'])

    LOG.info('copy cpython modules')
    modules = parameters['modules']
    excludes = [
        # Exclude idlelib, lib2to3, tkinter, and turtledemo.
        modules / 'idlelib',
        modules / 'lib2to3',
        modules / 'tkinter',
        modules / 'turtledemo',
        # Exclude tests.
        modules / 'ctypes/test',
        modules / 'distutils/tests',
        modules / 'sqlite3/test',
        modules / 'test',
        modules / 'unittest/test',
        # Exclude site-packages (you will have to cherry-pick them).
        modules / 'site-packages',
    ]
    rsync([modules], parameters['//base:build_rootfs'],
          relative=True, excludes=excludes, sudo=True)

    LOG.info('copy pth files')
    pths = list((modules / 'site-packages').glob('*.pth'))
    rsync(pths, parameters['//base:build_rootfs'], relative=True, sudo=True)

    LOG.info('copy cpython binaries')
    bins = parameters['prefix'] / 'bin'
    bins = list(bins.glob('python%d*' % parameters['version'].major))
    rsync(bins, parameters['//base:build_rootfs'], relative=True, sudo=True)


(define_rule(final_tapeout.__name__)
 .with_doc(final_tapeout.__doc__)
 .with_build(final_tapeout)
 .depend('build')
 .reverse_depend('//base:final_tapeout')
)
