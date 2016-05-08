"""Generic helper functions."""

__all__ = [
    # Generic scripting helpers.
    'call',
    'ensure_directory',
    'get_home',
    'git_clone',
    'run_commands',
    'sync_files',
    'tar_extract',
    'wget',
    # OS Package helpers.
    'install_packages',
    # Python-specific helpers.
    'python_build_package',
    'python_pip_install',
    'python_copy_package',
    # Helpers for the build image phase.
    'copy_libraries',
]

import itertools
import logging
import os.path
from pathlib import Path
from subprocess import check_call


LOG = logging.getLogger(__name__)


### Generic scripting helpers.


def call(args, **kwargs):
    """Log and then call subprocess.check_call."""
    if LOG.isEnabledFor(logging.DEBUG):
        LOG.debug('call: %s # cwd = %r', ' '.join(args), kwargs.get('cwd'))
    check_call(args, **kwargs)


def ensure_directory(path, mode=0o777):
    """Create a directory if it does not exists."""
    # exist_ok is added to Path.mkdir until Python 3.5 :(
    path = Path(path)
    if path.exists():
        if not path.is_dir():
            raise FileExistsError('not a directory: %s' % path)
        return
    LOG.debug('make directory: %s', path)
    path.mkdir(mode=mode, parents=True)


def get_home(user='~'):
    # Path.home() is defined in Python 3.5.
    return Path(os.path.expanduser(user))


def git_clone(repo, local_path=None, checkout=None):
    if local_path and local_path.exists():
        if not local_path.is_dir():
            raise FileExistsError('not a directory: %s' % local_path)
    else:
        cmd = ['git', 'clone', repo]
        if local_path:
            cmd.append(local_path.name)
            cwd = str(local_path.parent)
        else:
            cwd = None
        call(cmd, cwd=cwd)
    if checkout:
        call(['git', 'checkout', checkout])


def run_commands(commands_str, path=None):
    cwd = str(path) if path else None
    for command in commands_str.split('\n'):
        command = command.strip().split()
        if command:
            call(command, cwd=cwd)


def sync_files(srcs, dst, *, includes=(), excludes=(), sudo=False):
    """Copy files with rsync."""
    cmd = ['rsync', '--archive', '--relative']
    if sudo:
        cmd.insert(0, 'sudo')
    for include in includes:
        cmd.extend(['--include', str(include)])
    for exclude in excludes:
        cmd.extend(['--exclude', str(exclude)])
    cmd.extend(map(str, srcs))
    cmd.append(str(dst))
    call(cmd)


def tar_extract(tarball_path, output_path=None):
    """Extract a tarball."""
    tarball_path = Path(tarball_path)
    name = tarball_path.name
    if name.endswith('.tar'):
        compress_flag = None
    elif name.endswith('.tar.bz2'):
        compress_flag = '--bzip2'
    elif name.endswith('.tar.gz') or name.endswith('.tgz'):
        compress_flag = '--gzip'
    elif name.endswith('.tar.xz'):
        compress_flag = '--xz'
    else:
        raise RuntimeError('cannot parse tarball suffix: %s' % tarball_path)
    cmd = ['tar', '--extract', '--file', str(tarball_path)]
    if compress_flag:
        cmd.append(compress_flag)
    if output_path:
        cmd.extend(['--directory', str(output_path)])
    LOG.info('extract %s', tarball_path)
    check_call(cmd)


def wget(uri, output_path=None):
    cmd = ['wget', uri]
    if output_path:
        cmd.extend(['--output-document', str(output_path)])
    LOG.info('download %s', uri)
    check_call(cmd)


### OS Package helpers.


def install_packages(pkgs):
    cmd = ['sudo', 'apt-get', 'install', '--yes']
    cmd.extend(pkgs)
    call(cmd)


### Python-specific helpers.


def python_build_package(parameters, package_name, src, build_src):
    LOG.info('build %s', package_name)

    # Just a sanity check...
    setup_py = src / 'setup.py'
    if not setup_py.is_file():
        raise FileNotFoundError(setup_py)

    python = (parameters['//shipyard/cpython:prefix'] /
              ('bin/python%d.%d' % parameters['//shipyard/cpython:version']))
    if not python.is_file():
        raise FileNotFoundError(python)

    # Copy src into build_src (and build from there).
    cmd = ['rsync', '--archive']
    excludes = [
        '*.egg-info',
        '*.pyc',
        '.git',
        '.svn',
        '__pycache__',
        'build',
        'dist',
    ]
    for exclude in excludes:
        cmd.extend(['--exclude', exclude])
    # NOTE: Appending slash to src is a rsync trick.
    cmd.extend(['%s/' % src, str(build_src)])
    call(cmd)

    if not (build_src / 'build').exists():
        call([str(python), 'setup.py', 'build'], cwd=str(build_src))

    site_packages = python_get_site_packages(parameters)
    if not list(site_packages.glob('%s*' % package_name)):
        call(['sudo', str(python), 'setup.py', 'install'], cwd=str(build_src))


def python_pip_install(parameters, package_name):
    pip = (parameters['//shipyard/cpython:prefix'] /
           ('bin/pip%d.%d' % parameters['//shipyard/cpython:version']))
    if not pip.is_file():
        raise FileNotFoundError(pip)
    site_packages = python_get_site_packages(parameters)
    if not list(site_packages.glob('%s*' % package_name)):
        LOG.info('install %s', package_name)
        call(['sudo', str(pip), 'install', package_name])


def python_copy_package(parameters, package_name, patterns=()):
    LOG.info('copy %s', package_name)
    site_packages = python_get_site_packages(parameters)
    if not site_packages.is_dir():
        raise FileNotFoundError('not a directory: %s' % site_packages)
    dirs = list(site_packages.glob('%s*' % package_name))
    dirs.extend(
        itertools.chain.from_iterable(map(site_packages.glob, patterns)))
    sync_files(dirs, parameters['//shipyard:build_rootfs'], sudo=True)


def python_get_site_packages(parameters):
    return (
        parameters['//shipyard/cpython:prefix'] /
        ('lib/python%d.%d/site-packages' %
         parameters['//shipyard/cpython:version'])
    )


### Helpers for the build image phase.


def copy_libraries(parameters, libnames,
                   lib_dir='/usr/lib/x86_64-linux-gnu'):
    lib_dir = Path(lib_dir)
    libs = list(itertools.chain.from_iterable(
        lib_dir.glob('%s*' % name) for name in libnames))
    sync_files(libs, parameters['//shipyard:build_rootfs'], sudo=True)
