__all__ = [
    'add_arguments',
    'process_arguments',
    # Scripting helpers.
    'execute',
    'execute_many',
    'is_gzipped',
    'remove_tree',
    'systemctl',
]

import logging
from functools import partial
from subprocess import call, check_call, check_output


LOG = logging.getLogger(__name__)
LOG_FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'


DRY_RUN = False


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


def is_gzipped(path):
    output = execute(['file', path], return_output=True)
    return output and b'gzip compressed data' in output


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
