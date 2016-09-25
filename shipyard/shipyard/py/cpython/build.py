"""Build CPython from source."""

import logging
from collections import namedtuple
from pathlib import Path

from foreman import define_parameter, define_rule, decorate_rule
from shipyard import (
    execute,
    install_packages,
    pod,
    rsync,
    tapeout_libraries,
)

from shipyard import define_archive, py


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


define_archive(
    uri='https://www.python.org/ftp/python/3.5.1/Python-3.5.1.tar.xz',
    filename='Python-3.5.1.tar.xz',
    output='Python-3.5.1',
    derive_dst_path=lambda ps: ps['//base:build'] / 'py/cpython',
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
     ps['//base:build'] / 'py/cpython' / ps['archive_info'].output)
)


@decorate_rule('//base:build',
               'download')
def build(parameters):
    """Build CPython from source."""

    src_path = parameters['build_src']

    if not (src_path / 'Makefile').exists():
        install_packages(parameters['deps'])

        LOG.info('configure cpython')
        cmd = ['./configure', '--prefix', parameters['prefix']]
        execute(cmd, cwd=src_path)

    if not (src_path / 'python').exists():
        LOG.info('build cpython')
        execute(['make'], cwd=src_path)
        LOG.info('install cpython')
        execute(['sudo', 'make', 'install'], cwd=src_path)


# NOTE: All Python module's `tapeout` rules should reverse depend on
# this rule (and `//base:tapeout`, too).
def tapeout(parameters):
    """Join point of all Python module's `tapeout` rule."""

    LOG.info('copy cpython runtime libraries')
    tapeout_libraries(
        parameters, '/usr/lib/x86_64-linux-gnu', parameters['libs'])

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
    rsync([modules], parameters['//base:rootfs'],
          relative=True, excludes=excludes, sudo=True)

    LOG.info('copy pth files')
    pths = list((modules / 'site-packages').glob('*.pth'))
    rsync(pths, parameters['//base:rootfs'], relative=True, sudo=True)

    LOG.info('copy cpython binaries')
    bins = parameters['prefix'] / 'bin'
    bins = list(bins.glob('python%d*' % parameters['version'].major))
    rsync(bins, parameters['//base:rootfs'], relative=True, sudo=True)


(define_rule(tapeout.__name__)
 .with_doc(tapeout.__doc__)
 .with_build(tapeout)
 .depend('build')
 .reverse_depend('//base:tapeout')
)


@decorate_rule('build')
def install_cython(parameters):
    """Install (latest) Cython."""
    py.pip_install(parameters, 'cython')


pod.define_image(pod.Image(
    label_name='cpython',
    make_manifest=py.make_manifest,
    depends=['tapeout'],
))
