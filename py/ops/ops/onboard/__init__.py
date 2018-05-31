"""ops-onboard scripts."""

from pathlib import Path

from garage import apps
from garage import scripts

from . import alerts, deps, locks, pods, repos


@apps.with_prog('list')
@apps.with_help('list deployed images')
def list_images(args):
    """List deployed images."""
    table = repos.Repo(args.root).get_images()
    for image_id in sorted(table):
        podvs = table[image_id]
        if podvs:
            podvs = ' '.join('%s@%s' % pv for pv in podvs)
            print('%s %s' % (image_id, podvs))
        else:
            print(image_id)
    return 0


@apps.with_help('manage deployed images')
@apps.with_apps(
    'operation', 'operation on images',
    list_images,
)
def images(args):
    """Managa deployed images."""
    return args.operation(args)


@apps.with_prog('list')
@apps.with_help('list allocated and static ports')
def list_ports(args):
    """List ports allocated to deployed pods."""
    for port in repos.Repo(args.root).get_ports():
        print('%s@%s%s%s %s %d' % (
            port.pod_name,
            port.pod_version,
            ' ' if port.instance else '',
            port.instance or '',
            port.name,
            port.port,
        ))
    return 0


@apps.with_help('manage host ports')
@apps.with_apps(
    'operation', 'operation on ports',
    list_ports,
)
def ports(args):
    """Manage host ports allocated to pods."""
    return args.operation(args)


@apps.with_prog('ops-onboard')
@apps.with_argument(
    '--dry-run', action='store_true',
    help='do not execute commands',
)
@apps.with_argument(
    '--root', metavar='PATH', type=Path, default=Path('/var/lib/ops'),
    help='set root directory of repos (default %(default)s)'
)
@apps.with_apps(
    'entity', 'system entity to be operated on',
    alerts.alerts,
    deps.deps,
    images,
    ports,
    pods.pods,
)
def main(args):
    """Onboard operations tool."""
    with scripts.dry_run(args.dry_run):
        scripts.ensure_not_root()
        if getattr(args, 'no_locking_required', False):
            lock = None
        else:
            lock = locks.FileLock(repos.Repo.get_lock_path(args.root))
        if not lock or lock.acquire():
            try:
                return args.entity(args)
            finally:
                if lock:
                    lock.release()
        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.error('cannot lock repo: %s', args.root)
            return 1


def run_main():
    apps.run(main)
