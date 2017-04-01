"""ops-mob scripts."""

__all__ = [
    'main',
]

from garage import cli, scripts
from garage.components import ARGS

from . import envs, keys


@cli.command('ops-mob')
@cli.argument('--dry-run', action='store_true', help='do not execute commands')
@cli.sub_command_info('entity', 'system entity to be operated on')
@cli.sub_command(envs.envs)
@cli.sub_command(keys.keys)
def main(args: ARGS):
    """MOB operations tool."""
    with scripts.dry_run(args.dry_run):
        scripts.ensure_not_root()
        return args.entity()
