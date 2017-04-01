__all__ = [
    'envs',
]

from argparse import Namespace
from pathlib import Path
import datetime
import logging
import os

import yaml

from garage import cli, scripts
from garage.components import ARGS

from . import cloudinit, keys


LOG = logging.getLogger(__name__)


# Root directory of all environments
OPS_ROOT = scripts.ensure_path(os.environ.get('OPS_ROOT'))
# Currently activated environment
OPS_ENV = os.environ.get('OPS_ENV')


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

    # Generate SSH host and user keys
    scripts.mkdir(env_dir / 'keys')
    keys_current_dir = env_dir / 'keys' / 'current'
    # Use YYYYMM for keys directory name
    keys_dir = env_dir / 'keys' / datetime.date.today().strftime('%Y%m')
    if keys_current_dir.exists():
        LOG.info('refuse to overwrite %s', keys_current_dir)
    elif keys_dir.exists():
        LOG.info('refuse to overwrite %s', keys_dir)
    else:
        LOG.info('generate keys')
        new_args = Namespace(output_dir=keys_dir, **args.__dict__)
        returncode = keys.generate_host_key(args=new_args)
        if returncode != 0:
            LOG.error('err when generating host keys')
            return returncode
        returncode = keys.generate_user_key(args=new_args)
        if returncode != 0:
            LOG.error('err when generating user key')
            return returncode
        scripts.symlink(keys_dir.name, keys_current_dir)

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


@cli.command('gen-user-data', help='generate cloud-init user data')
@cli.argument(
    '--env', required=not OPS_ENV, default=OPS_ENV,
    help='''choose an environment (default from OPS_ENV environment
            variable, which is %(default)s)'''
)
@cli.argument('config', type=Path, help='set config file path')
def generate_user_data(args: ARGS):
    """Generate cloud-init user data."""

    config = yaml.load(args.config.read_text())

    cloudinit_args = {}

    env_dir = args.root / ENVS_DIR / args.env

    keys_dir = env_dir / 'keys' / 'current'
    cloudinit_args['ssh_host_key'] = [
        (
            algorithm,
            keys_dir / keys.ssh_host_key_filename(algorithm),
            keys_dir / (keys.ssh_host_key_filename(algorithm) + '.pub'),
        )
        for algorithm, _ in keys.HOST_KEYS
    ]
    public_key = keys.ssh_user_key_filename(keys.USER_KEY_ALGORITHM) + '.pub'
    cloudinit_args['ssh_authorized_key'] = [
        keys_dir / public_key,
    ]

    local_vm = config.get('local-vm')
    if local_vm:
        cloudinit_args['local_vm'] = (
            local_vm['name'],
            local_vm['name'] + '.local',
            local_vm['network-interface'],
            local_vm['ip-address'],
        )

    cloudinit_args['output'] = env_dir / 'cloud-init' / config['output']

    return cloudinit.generate_user_data(
        args=Namespace(**cloudinit_args, **args.__dict__))


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
@cli.sub_command(generate_user_data)
def envs(args: ARGS):
    """Manage ops environments."""
    return args.operation()
