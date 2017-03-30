"""ops-mob scripts."""

__all__ = [
    'main',
]

from garage import cli, scripts
from garage.components import ARGS


@cli.command('ops-mob')
@cli.argument('--dry-run', action='store_true', help='do not execute commands')
def main(args: ARGS):
    """MOB operations tool."""
    with scripts.dry_run(args.dry_run):
        return 0
