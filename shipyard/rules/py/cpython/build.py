"""Build CPython from source."""

from collections import namedtuple
from pathlib import Path
import logging

from foreman import define_parameter, get_relpath, rule

from garage import scripts

from templates import define_archive, tapeout_files


LOG = logging.getLogger(__name__)


### CPython build parameters


Version = namedtuple('Version', 'major minor')
(define_parameter.namedtuple_typed(Version, 'version')
 .with_doc('CPython version.')
 .with_default(Version('3', '6')))


define_archive(
    uri='https://www.python.org/ftp/python/3.6.1/Python-3.6.1rc1.tar.xz',
    filename='Python-3.6.1rc1.tar.xz',
    output='Python-3.6.1rc1',
    checksum='md5-5919c290d3727d81c3472e6c46fd78b6',
)


define_parameter.path_typed('prefix').with_default(Path('/usr/local'))


define_parameter.list_typed('configuration').with_default([
    '--enable-ipv6',
    '--enable-loadable-sqlite-extensions',
    '--with-computed-gotos',
    '--with-dbmliborder=bdb:gdbm',
    '--with-fpectl',
    '--with-system-expat',
    '--with-system-ffi',
    '--with-system-libmpdec',
    '--without-ensurepip',
])


### Dependencies


# This list is derived from running `apt-get build-dep python3.6` on
# Ubuntu 16.10 (not all packages are included)
(define_parameter
 .list_typed('distro_packages')
 .with_doc('Build-time Debian packages.')
 .with_default([
     # Build tool
     'autoconf',
     'automake',
     'autotools-dev',
     'binutils',
     'cpp',
     'g++',
     'gcc',
     'libtool',
     'm4',
     'make',
     'pkg-config',
     # Libraries
     'libatomic1',
     'libc6-dev',
     'libmpc3',
     'libmpdec-dev',
     'libmpfr4',
     'libmpx2',
     'libsigsegv2',
     # Compression
     'libbz2-dev',
     'liblzma-dev',
     'zlib1g-dev',
     # Console
     'libncursesw5-dev',
     'libreadline-dev',
     # Database
     'libdb-dev',
     'libgdbm-dev',
     'libsqlite3-dev',
     # FFI
     'libffi-dev',
     # Network
     'libssl-dev',
     # XML
     'libexpat1-dev',
     'libxml2',  # Do we really need this?
 ]))


### Build artifacts


(define_parameter.path_typed('python')
 .with_doc('Path to CPython interpreter.')
 .with_derive(lambda ps: ps['prefix'] / ('bin/python%s.%s' % ps['version'])))


(define_parameter.path_typed('pip')
 .with_doc('Path to pip.')
 .with_derive(lambda ps: ps['prefix'] / ('bin/pip%s.%s' % ps['version'])))


(define_parameter.path_typed('modules')
 .with_doc('Path to site-packages directory.')
 .with_derive(lambda ps: ps['prefix'] / ('lib/python%s.%s' % ps['version'])))


### Build rules


@rule.depend('//base:build')
@rule.depend('download')
def build(parameters):
    """Build CPython from source."""

    with scripts.using_sudo():
        scripts.apt_get_install(parameters['distro_packages'])

    drydock_src = (parameters['//base:drydock'] / get_relpath() /
                   parameters['archive_info'].output)
    with scripts.directory(drydock_src):

        if not (drydock_src / 'Makefile').exists():
            LOG.info('configure cpython build')
            cmd = ['./configure', '--prefix', parameters['prefix']]
            cmd.extend(parameters['configuration'])
            if parameters['//base:release']:
                cmd.extend(['--enable-optimizations', '--with-lto'])
            scripts.execute(cmd)

        if not (drydock_src / 'python').exists():
            LOG.info('build cpython')
            scripts.execute(['make'])

            LOG.info('install cpython')
            with scripts.using_sudo():
                # (Probably a bug?) When optimizations are enabled, this
                # will re-run `make run_profile_task`
                scripts.execute(['make', 'install'])


@rule.depend('build')
@rule.reverse_depend('//base:tapeout')
def tapeout(parameters):
    """Tape-out CPython.

       NOTE: All Python module's `tapeout` rules should reverse depend
       on this rule.
    """

    LOG.info('tapeout cpython modules')
    modules = parameters['modules']
    excludes = [
        # Exclude idlelib, lib2to3, tkinter, and turtledemo
        modules / 'idlelib',
        modules / 'lib2to3',
        modules / 'tkinter',
        modules / 'turtledemo',
        # Exclude tests
        modules / 'ctypes/test',
        modules / 'distutils/tests',
        modules / 'sqlite3/test',
        modules / 'test',
        modules / 'unittest/test',
        # Exclude site-packages (you will have to cherry-pick them)
        modules / 'site-packages',
    ]
    tapeout_files(parameters, [modules], excludes=excludes)

    # We would tape out pth files for you, but remember, you still have
    # to cherry pick modules under site-packages
    pths = list((modules / 'site-packages').glob('*.pth'))
    tapeout_files(parameters, pths)

    LOG.info('tapeout cpython executables')
    execs = parameters['prefix'] / 'bin'
    execs = list(execs.glob('python%s*' % parameters['version'].major))
    tapeout_files(parameters, execs)
