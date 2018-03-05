"""ops-mob scripts."""

__all__ = [
    'main',
]

from garage import apps
from garage import scripts

from . import cloudinit, envs, keys, localvms, openvpn, pods


@apps.with_prog('ops-mob')
@apps.with_argument(
    '--dry-run', action='store_true',
    help='do not execute commands',
)
@apps.with_apps(
    'entity', 'system entity to be operated on',
    envs.envs,
    cloudinit.cloudinit,
    keys.keys,
    localvms.localvms,
    openvpn.openvpn,
    pods.pods,
)
def main(args):
    """MOB operations tool."""
    with scripts.dry_run(args.dry_run):
        scripts.ensure_not_root()
        return args.entity(args)
