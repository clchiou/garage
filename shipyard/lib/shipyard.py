"""Generic helper functions."""

__all__ = [
    # Generic scripting helpers.
    'ensure_directory',
    'execute',
    'git_clone',
    'rsync',
    'run_commands',
    'tar_extract',
    'wget',
    # OS Package helpers.
    'install_packages',
    # Python-specific helpers.
    'python_copy_source',
    'python_build_package',
    'python_copy_and_build_package',
    'python_pip_install',
    'python_copy_package',
    # Helpers for the build image/pod phases.
    'build_appc_image',
    'copy_libraries',
    'render_appc_manifest',
    'render_bundle_files',
    'render_template',
]

import hashlib
import itertools
import json
import logging
from contextlib import ExitStack
from pathlib import Path
from subprocess import PIPE, Popen, check_call, check_output

from foreman import to_path


LOG = logging.getLogger(__name__)


### Generic scripting helpers.


def ensure_directory(path, mode=0o777):
    """Return True when the directory exists; else return false and
       create the directory.
    """
    # exist_ok is added to Path.mkdir until Python 3.5 :(
    path = Path(path)
    if path.exists():
        if not path.is_dir():
            raise FileExistsError('not a directory: %s' % path)
        return True
    LOG.debug('make directory: %s', path)
    path.mkdir(mode=mode, parents=True)
    return False


def execute(args, *, return_output=False, cwd=None):
    """Log and then call subprocess.check_call."""
    args = list(map(str, args))
    if LOG.isEnabledFor(logging.DEBUG):
        LOG.debug('execute: %s # cwd = %r', ' '.join(args), cwd)
    if return_output:
        caller = check_output
    else:
        caller = check_call
    cwd = str(cwd) if cwd else None
    return caller(args, cwd=cwd)


def git_clone(repo, local_path=None, checkout=None):
    if local_path and local_path.exists():
        if not local_path.is_dir():
            raise FileExistsError('not a directory: %s' % local_path)
    else:
        cmd = ['git', 'clone', repo]
        if local_path:
            cmd.append(local_path.name)
        LOG.info('clone git repo %s', repo)
        cwd = local_path.parent if local_path else None
        execute(cmd, cwd=cwd)
    if checkout:
        LOG.info('checkout %s %s', repo, checkout)
        cwd = local_path if local_path else None
        execute(['git', 'checkout', checkout], cwd=cwd)


def run_commands(commands_str, path=None):
    for command in commands_str.split('\n'):
        command = command.strip().split()
        if command:
            execute(command, cwd=path)


def rsync(srcs, dst, *,
          relative=False,
          includes=(), excludes=(),
          sudo=False):
    if not srcs:
        LOG.warning('rsync: empty srcs: %r', srcs)
        return
    cmd = ['rsync', '--archive']
    if sudo:
        cmd.insert(0, 'sudo')
    if relative:
        cmd.append('--relative')
    for include in includes:
        cmd.extend(['--include', include])
    for exclude in excludes:
        cmd.extend(['--exclude', exclude])
    cmd.extend(srcs)
    cmd.append(dst)
    execute(cmd)


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
    cmd = ['tar', '--extract', '--file', tarball_path]
    if compress_flag:
        cmd.append(compress_flag)
    if output_path:
        cmd.extend(['--directory', output_path])
    LOG.info('extract %s', tarball_path)
    execute(cmd)


def wget(uri, output_path=None):
    cmd = ['wget', uri]
    if output_path:
        cmd.extend(['--output-document', output_path])
    LOG.info('download %s', uri)
    execute(cmd)


### OS Package helpers.


def install_packages(pkgs):
    if LOG.isEnabledFor(logging.INFO):
        LOG.info('install %s', ' '.join(pkgs))
    cmd = ['sudo', 'apt-get', 'install', '--yes']
    cmd.extend(pkgs)
    execute(cmd)


### Python-specific helpers.


def python_copy_source(parameters, package_name, src=None, build_src=None):
    LOG.info('copy source for %s', package_name)

    if not src:
        src = 'py/%s' % package_name
    if isinstance(src, str):
        src = parameters['//base:root'] / src

    if not build_src:
        build_src = package_name
    if isinstance(build_src, str):
        build_src = parameters['//base:build_src'] / build_src

    # Just a sanity check...
    setup_py = src / 'setup.py'
    if not setup_py.is_file():
        raise FileNotFoundError(str(setup_py))

    # Copy src into build_src (and build from there).
    # NOTE: Appending slash to src is a rsync trick.
    rsync(['%s/' % src], build_src, excludes=[
        '*.egg-info',
        '*.pyc',
        '.git',
        '.svn',
        '__pycache__',
        'build',
        'dist',
    ])

    return build_src


def python_build_package(parameters, package_name, build_src):
    LOG.info('build %s', package_name)
    python = parameters['//cpython:python']
    if not (build_src / 'build').exists():
        execute([python, 'setup.py', 'build'], cwd=build_src)
    site_packages = parameters['//cpython:modules'] / 'site-packages'
    if not list(site_packages.glob('%s*' % package_name)):
        execute(['sudo', '--preserve-env', python, 'setup.py', 'install'],
                cwd=build_src)


def python_copy_and_build_package(
        parameters, package_name, src=None, build_src=None):
    build_src = python_copy_source(parameters, package_name, src, build_src)
    python_build_package(parameters, package_name, build_src)


def python_pip_install(parameters, package_name, version=None):
    LOG.info('install %s with version %s', package_name, version)
    site_packages = parameters['//cpython:modules'] / 'site-packages'
    if not list(site_packages.glob('%s*' % package_name)):
        if version:
            target = '%s==%s' % (package_name, version)
        else:
            target = package_name
        execute(['sudo', parameters['//cpython:pip'], 'install', target])


def python_copy_package(parameters, package_name, patterns=()):
    LOG.info('copy %s', package_name)
    site_packages = parameters['//cpython:modules'] / 'site-packages'
    dirs = list(site_packages.glob('%s*' % package_name))
    dirs.extend(itertools.chain.from_iterable(
        map(site_packages.glob, patterns)))
    rsync(dirs, parameters['//base:build_rootfs'], relative=True, sudo=True)


### Helpers for the build image phase.


# TODO: Encrypt and/or sign the image.
def build_appc_image(src_dir, dst_dir):
    LOG.info('build appc image: %s -> %s', src_dir, dst_dir)

    for target in ('manifest', 'rootfs'):
        target = src_dir / target
        if not target.exists():
            raise FileNotFoundError(str(target))

    with ExitStack() as stack:
        proc_tar = stack.enter_context(Popen(
            ['tar', '--create', 'manifest', 'rootfs'],
            stdout=PIPE,
            cwd=str(src_dir),
        ))

        proc_gzip = stack.enter_context(Popen(
            ['gzip'],
            stdin=PIPE,
            stdout=stack.enter_context((dst_dir / 'image.aci').open('wb')),
        ))

        sha512 = hashlib.sha512()
        while True:
            data = proc_tar.stdout.read(4096)
            if not data:
                break
            sha512.update(data)
            proc_gzip.stdin.write(data)

        proc_tar.stdout.close()
        proc_gzip.stdin.close()

        (dst_dir / 'sha512').write_text('%s\n' % sha512.hexdigest())

        retcode = proc_tar.wait()
        if retcode != 0:
            raise RuntimeError('error in tar: rc=%d' % retcode)

        retcode = proc_gzip.wait()
        if retcode != 0:
            raise RuntimeError('error in gzip: rc=%d' % retcode)


def copy_libraries(parameters, lib_dir, libnames):
    lib_dir = Path(lib_dir)
    libs = list(itertools.chain.from_iterable(
        lib_dir.glob('%s*' % name) for name in libnames))
    rsync(libs, parameters['//base:build_rootfs'], relative=True, sudo=True)


def render_appc_manifest(parameters, manifest_label, template_vars=None):
    """Helper for creating appc image manifest."""
    render_template(
        parameters,
        to_path(manifest_label),
        parameters['//base:build_out'] / 'manifest',
        template_vars=template_vars,
    )


def render_bundle_files(parameters, label_path_pairs, template_vars=None):
    """Helper for creating some basic deployment bundle files by
       following some conventions.
    """

    template_vars = template_vars or {}

    if 'version' not in template_vars:
        version = parameters['version']
        if version is None:
            raise RuntimeError('no version is set')
        template_vars['version'] = version

    if 'sha512' not in template_vars:
        sha512_path = parameters['//base:output'] / 'sha512'
        if not sha512_path.is_file():
            raise FileExistsError('not a file: %s' % sha512_path)
        template_vars['sha512'] = sha512_path.read_text().strip()

    for label, path in label_path_pairs:
        render_template(parameters, to_path(label), path, template_vars)


def render_template(
        parameters, template_path, output_path, template_vars=None):
    LOG.info('render %s', template_path)

    python = parameters['//host/cpython:python']
    if not python.is_file():
        raise FileNotFoundError(str(python))

    render = Path(__file__).parent / 'render.py'
    if not render.is_file():
        raise FileNotFoundError(str(render))

    cmd = [python, render]
    if template_vars:
        for name, value in template_vars.items():
            cmd.append('--json-value')
            cmd.append(name)
            cmd.append(json.dumps(value))
    cmd.append('--output')
    cmd.append(output_path.absolute())
    cmd.append(template_path.relative_to(Path.home()))

    execute(cmd, cwd=Path.home())
