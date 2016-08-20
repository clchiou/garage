__all__ = [
    'add_arguments',
    'ensure_not_root',
    'process_arguments',
    # Scripting helpers.
    'execute',
    'execute_many',
    'remove_tree',
    'systemctl',
    'tar_extract',
    'wget',
]

import getpass
import logging
from functools import partial
from subprocess import call, check_call, check_output


LOG = logging.getLogger(__name__)
LOG_FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'


DRY_RUN = False


def ensure_not_root():
    if getpass.getuser() == 'root':
        raise RuntimeError('run by root')


def add_arguments(parser):
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help="""verbose output""")
    parser.add_argument(
        '--dry-run', action='store_true',
        help="""do not actually run commands""")


def process_arguments(_, args):
    if args.verbose > 0:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(level=level, format=LOG_FORMAT)
    global DRY_RUN
    DRY_RUN = bool(args.dry_run)


### Scripting helpers.


def execute(cmd, *, cwd=None, return_output=False, check=True):
    cmd = list(map(str, cmd))
    cwd = str(cwd) if cwd is not None else None
    if LOG.isEnabledFor(logging.DEBUG):
        LOG.debug('execute: %s # cwd = %s', ' '.join(cmd), cwd)
    if DRY_RUN:
        return
    if return_output:
        caller = check_output
    elif check:
        caller = check_call
    else:
        caller = call
    return caller(cmd, cwd=cwd)


def execute_many(cmds, *, cwd=None):
    for cmd in cmds:
        execute(cmd, cwd=cwd)


def remove_tree(path):
    execute(['sudo', 'rm', '--force', '--recursive', path])


def systemctl(command, name, *, sudo=True, **kwargs):
    cmd = ['systemctl', '--quiet', command, name]
    if sudo:
        cmd.insert(0, 'sudo')
    return execute(cmd, **kwargs)


systemctl.enable = partial(systemctl, 'enable')
systemctl.disable = partial(systemctl, 'disable')
systemctl.is_enabled = partial(systemctl, 'is-enabled', sudo=False)


systemctl.start = partial(systemctl, 'start')
systemctl.stop = partial(systemctl, 'stop')
systemctl.is_active = partial(systemctl, 'is-active', sudo=False)


def tar_extract(tarball_path, *, sudo=False, tar_extra_args=(), **kwargs):
    cmd = ['tar', '--extract', '--file', tarball_path]
    if sudo:
        cmd.insert(0, 'sudo')

    output = execute(['file', tarball_path], return_output=True)
    if not output:
        raise RuntimeError('command `file` no output: %s' % tarball_path)
    if b'gzip compressed data' in output:
        cmd.append('--gzip')
    elif b'bzip2 compressed data' in output:
        cmd.append('--bzip2')
    elif b'XZ compressed data' in output:
        cmd.append('--xz')

    cmd.extend(tar_extra_args)

    return execute(cmd, **kwargs)


def wget(uri, output_path, **kwargs):
    cmd = [
        'wget',
        '--no-verbose',  # No progress bar.
        '--output-document', output_path,
        uri,
    ]
    return execute(cmd, **kwargs)
