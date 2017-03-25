import logging

from garage import cli, scripts
from garage.components import ARGS

from .deps import deps


logging.getLogger(__name__).addHandler(logging.NullHandler())


@cli.command('ops')
@cli.argument('--dry-run', action='store_true', help='do not execute commands')
@cli.sub_command_info('entity', 'system entity to be operated on')
@cli.sub_command(deps)
def main(args: ARGS):
    """Operations tool."""
    with scripts.dry_run(args.dry_run):
        scripts.ensure_not_root()
        return args.entity()
