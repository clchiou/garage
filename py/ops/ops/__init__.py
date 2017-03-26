from pathlib import Path
import logging

from garage import cli, scripts
from garage.components import ARGS

from . import deps, locks, pods, repos


logging.getLogger(__name__).addHandler(logging.NullHandler())


@cli.command('list', help='list allocated ports')
def list_ports(args: ARGS):
    """List ports allocated to deployed pods."""
    for port in repos.Repo(args.root).get_ports():
        print('%s:%s %s %d' %
              (port.pod_name, port.pod_version, port.name, port.port))
    return 0


@cli.command(help='manage host ports')
@cli.sub_command_info('operation', 'operation on ports')
@cli.sub_command(list_ports)
def ports(args: ARGS):
    """Manage host ports allocated to pods."""
    return args.operation()


@cli.command('ops')
@cli.argument('--dry-run', action='store_true', help='do not execute commands')
@cli.argument(
    '--root', metavar='PATH', type=Path, default=Path('/var/lib/ops'),
    help='set root directory of repos (default %(default)s)'
)
@cli.sub_command_info('entity', 'system entity to be operated on')
@cli.sub_command(deps.deps)
@cli.sub_command(ports)
@cli.sub_command(pods.pods)
def main(args: ARGS):
    """Operations tool."""
    with scripts.dry_run(args.dry_run):
        scripts.ensure_not_root()
        if getattr(args, 'no_locking_required', False):
            lock = None
        else:
            lock = locks.FileLock(repos.Repo.get_lock_path(args.root))
        if not lock or lock.acquire():
            try:
                return args.entity()
            finally:
                if lock:
                    lock.release()
        else:
            logger = logging.getLogger(__name__)
            logger.error('cannot lock repo: %s', args.root)
            return 1
