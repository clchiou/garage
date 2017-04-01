__all__ = [
    'envs',
]

from argparse import Namespace
from pathlib import Path
import datetime
import logging
import os

from garage import cli, scripts
from garage.components import ARGS

from . import keys


LOG = logging.getLogger(__name__)


OPS_ROOT = scripts.ensure_path(os.environ.get('OPS_ROOT'))


ENVS_DIR = 'envs'


@cli.command('list', help='list environments')
def list_envs(args: ARGS):
    """List environments."""
    for filename in sorted((args.root / ENVS_DIR).iterdir()):
        print(filename.name)
    return 0


@cli.command('gen', help='generate environment')
@cli.argument(
    '--overwrite', action='store_true',
    help='instruct scripts to overwrite existing files',
)
@cli.argument('env', help='set name of the new environment')
def generate(args: ARGS):
    """Generate environment."""

    def check_overwrite(path):
        if path.exists():
            if args.overwrite:
                LOG.warning('overwrite %s', path)
                return True
            else:
                LOG.info('refuse to overwrite %s', path)
                return False
        else:
            return True

    generated_at = datetime.datetime.utcnow().isoformat()

    templates_dir = Path(__file__).parent / 'templates'

    env_dir = args.root / ENVS_DIR / args.env
    scripts.mkdir(env_dir)

    scripts.mkdir(env_dir / 'cloud-init')
    # TODO: Generate cloud-init files

    # Generate SSH host and user keys
    scripts.mkdir(env_dir / 'keys')
    keys_current_dir = env_dir / 'keys/current'
    if keys_current_dir.exists():
        LOG.info('refuse to overwrite %s', keys_current_dir)
    else:
        LOG.info('generate keys')
        new_args = Namespace(output_dir=keys_current_dir, **args.__dict__)
        returncode = keys.generate_host_key(args=new_args)
        if returncode != 0:
            LOG.error('err when generating host keys')
            return returncode
        returncode = keys.generate_user_key(args=new_args)
        if returncode != 0:
            LOG.error('err when generating user key')
            return returncode

    scripts_dir = env_dir / 'scripts'
    scripts.mkdir(scripts_dir)

    # Generate scripts/env.sh
    env_sh = scripts_dir / 'env.sh'
    if check_overwrite(env_sh):
        LOG.info('generate env.sh')
        scripts.ensure_contents(
            env_sh,
            (templates_dir / 'env.sh').read_text().format(
                generated_at=generated_at,
                env=args.env,
                private_key=env_dir / 'keys/current/id_ecdsa',
                inventory=env_dir / 'hosts',
            ),
        )

    return 0


@cli.command(help='manage ops environments')
@cli.argument(
    '--root', metavar='PATH', type=Path,
    required=not OPS_ROOT, default=OPS_ROOT,
    help='''set root directory of ops data (default from OPS_ROOT
            environment variable, which is %(default)s)'''
)
@cli.sub_command_info('operation', 'operation on environment')
@cli.sub_command(list_envs)
@cli.sub_command(generate)
def envs(args: ARGS):
    """Manage ops environments."""
    return args.operation()
