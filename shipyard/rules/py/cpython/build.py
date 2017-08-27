"""Build CPython from source."""

from collections import namedtuple
from pathlib import Path
import logging

from foreman import define_parameter, get_relpath, rule

from garage import scripts

from templates import pods
from templates.common import define_archive, define_distro_packages
from templates.utils import tapeout_files


LOG = logging.getLogger(__name__)


### CPython build parameters


(define_parameter.bool_typed('shared')
 .with_doc('Enable building libpython.so (if you are embedding Python).')
 .with_default(False))


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
])


### Dependencies


# This list is derived from running `apt-get build-dep python3.6` on
# Ubuntu 16.10 (not all packages are included)
define_distro_packages([
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
])


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


@rule
@rule.depend('//base:build')
@rule.depend('install_packages')
@rule.depend('download')
def build(parameters):
    """Build CPython from source."""
    drydock_src = (parameters['//base:drydock'] / get_relpath() /
                   parameters['archive_info'].output)
    with scripts.directory(drydock_src):

        if not (drydock_src / 'Makefile').exists():
            LOG.info('configure cpython build')
            cmd = ['./configure', '--prefix', parameters['prefix']]
            cmd.extend(parameters['configuration'])
            # TODO Re-enable optimizer when the build script bug is
            # fixed (`make install` re-runs `make run_profile_task`
            # again).
            #if parameters['//base:release']:
            #    cmd.extend(['--enable-optimizations', '--with-lto'])
            if parameters['shared']:
                cmd.append('--enable-shared')
            scripts.execute(cmd)

        if not (drydock_src / 'python').exists():
            LOG.info('build cpython')
            scripts.execute(['make'])

            LOG.info('install cpython')
            with scripts.using_sudo():
                # (Probably a bug?) When optimizations are enabled, this
                # will re-run `make run_profile_task`
                scripts.execute(['make', 'install'])
                if parameters['shared']:
                    scripts.execute(['ldconfig'])

    # Custom-built Python sometimes creates "pythonX.Ym" rather than
    # "pythonX.Y" header directory
    header_dir = (
        parameters['prefix'] / 'include' /
        ('python%s.%s' % parameters['version'])
    )
    if not header_dir.exists():
        alt_header_dir = header_dir.with_name(
            'python%s.%sm' % parameters['version'])
        scripts.ensure_directory(alt_header_dir)
        LOG.info('symlink cpython headers')
        with scripts.using_sudo():
            scripts.symlink(alt_header_dir.name, header_dir)

    # Same for libpython
    if parameters['shared']:
        libpython = (
            parameters['prefix'] / 'lib' /
            ('libpython%s.%s.so' % parameters['version'])
        )
        if not libpython.exists():
            alt_libpython = libpython.with_name(
                'libpython%s.%sm.so' % parameters['version'])
            scripts.ensure_file(alt_libpython)
            LOG.info('symlink cpython library')
            with scripts.using_sudo():
                scripts.symlink(alt_libpython.name, libpython)


@rule
@rule.depend('build')
@rule.reverse_depend('//base:tapeout')
def tapeout(parameters):
    """Tape-out CPython.

    NOTE: All Python module's `tapeout` rules should reverse depend on
    this rule.
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


### Python pod build rules (useful for testing).


@pods.app_specifier
def python_app(parameters):
    """Default App object for Python container image."""
    return pods.App(
        name='python',
        exec=[str(parameters['python'])],
        environment={
            # Unfortunately I can't make the default encoding right
            # inside a container (`locale.getpreferredencoding(False)`
            # is always 'ANSI_X3.4-1968').  So you have to specify
            # encoding whenever you open a file.  Here we specify
            # PYTHONIOENCODING so that sys.stdin and sys.stdout will be
            # default to UTF-8.
            'PYTHONIOENCODING': 'UTF-8',
        },
    )


@pods.image_specifier
def python_image(parameters):
    """Default Python container image."""
    return pods.Image(
        name='python',
        app=parameters['python_app'],
    )


@pods.pod_specifier
def python_pod(parameters):
    """Trivial Python pod only useful for testing."""
    return pods.Pod(
        name='python',
        images=[parameters['python_image']],
    )


python_image.specify_image.depend('python_app/specify_app')
python_pod.specify_pod.depend('python_image/specify_image')


python_image.write_manifest.depend('tapeout')
