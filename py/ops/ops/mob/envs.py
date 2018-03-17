__all__ = [
    'envs',
]

from argparse import Namespace
from pathlib import Path
import datetime
import logging
import os

import yaml

from garage import apps
from garage import scripts

from . import cloudinit, keys, openvpn


LOG = logging.getLogger(__name__)


# Root directory of all environments
OPS_ROOT = scripts.ensure_path(os.environ.get('OPS_ROOT'))
with_argument_root = apps.with_argument(
    '--root', metavar='PATH', type=Path,
    required=not OPS_ROOT, default=OPS_ROOT,
    help='''set root directory of ops data (default from OPS_ROOT
            environment variable, which is %(default)s)'''
)


# Currently activated environment
OPS_ENV = os.environ.get('OPS_ENV')
with_argument_env = apps.with_argument(
    '--env', required=not OPS_ENV, default=OPS_ENV,
    help='''choose an environment (default from OPS_ENV environment
            variable, which is %(default)s)'''
)


ENVS_DIR = 'envs'


@apps.with_prog('list')
@apps.with_help('list environments')
def list_envs(args):
    """List environments."""
    for filename in sorted((args.root / ENVS_DIR).iterdir()):
        print(filename.name)
    return 0


@apps.with_prog('gen')
@apps.with_help('generate environment')
@apps.with_argument('env', help='set name of the new environment')
def generate(args):
    """Generate environment."""

    generated_at = datetime.datetime.utcnow().isoformat()

    # Use YYYYMM in some directory names
    yyyymm = datetime.date.today().strftime('%Y%m')

    templates_dir = Path(__file__).parent / 'templates'

    env_dir = args.root / ENVS_DIR / args.env
    scripts.mkdir(env_dir)

    # cloud-init (at the moment just an empty directory)
    scripts.mkdir(env_dir / 'cloud-init')

    # Generate SSH host and user keys
    scripts.mkdir(env_dir / 'keys')
    keys_current_dir = env_dir / 'keys' / 'current'
    keys_dir = env_dir / 'keys' / yyyymm
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

    # OpenVPN stuff

    openvpn_dir = env_dir / 'openvpn'
    scripts.mkdir(openvpn_dir)

    cadir = openvpn_dir / 'cadir'
    if cadir.exists():
        LOG.info('refuse to overwrite %s', cadir)
    else:
        LOG.info('generate easy-rsa cadir')
        scripts.execute(['make-cadir', cadir])

    scripts.mkdir(openvpn_dir / 'clients')

    scripts.mkdir(openvpn_dir / 'servers' / yyyymm)
    servers_current_dir = openvpn_dir / 'servers' / 'current'
    if not servers_current_dir.exists():
        scripts.symlink(yyyymm, servers_current_dir)

    # scripts

    scripts_dir = env_dir / 'scripts'
    scripts.mkdir(scripts_dir)

    # Generate scripts/env.sh
    env_sh = scripts_dir / 'env.sh'
    if env_sh.exists():
        LOG.warning('overwrite %s', env_sh)
    LOG.info('generate env.sh')
    scripts.ensure_contents(
        env_sh,
        (templates_dir / 'env.sh').read_text().format(
            generated_at=generated_at,
            root=args.root,
            env=args.env,
            private_key=env_dir / 'keys/current/id_ecdsa',
            inventory=env_dir / 'hosts.yaml',
        ),
    )

    return 0


@apps.with_prog('gen-user-data')
@apps.with_help('generate cloud-init user data')
@with_argument_env
@apps.with_argument('config', type=Path, help='set config file path')
def generate_user_data(args):
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
            local_vm['hostname'],
            local_vm['hostname'] + '.local',
            local_vm['network-interface'],
            local_vm['ip-address'],
        )
    else:
        cloudinit_args['local_vm'] = None

    password = config.get('password')
    if password:
        cloudinit_args['password'] = password

    cloudinit_args['output'] = env_dir / 'cloud-init' / config['output']

    return cloudinit.generate_user_data(args=Namespace(
        **cloudinit_args,
        **args.__dict__,
    ))


@apps.with_prog('copy-client')
@apps.with_help('copy generated openvpn client data')
@with_argument_env
@apps.with_argument('client', help='provide client name')
def copy_client(args):
    """Copy generated OpenVPN client data to another directory."""
    env_dir = args.root / ENVS_DIR / args.env
    return openvpn.copy_client(args=Namespace(
        cadir=env_dir / 'openvpn' / 'cadir',
        target=env_dir / 'openvpn' / 'clients',
        **args.__dict__,
    ))


@apps.with_prog('copy-server')
@apps.with_help('copy generated openvpn server data')
@with_argument_env
def copy_server(args):
    """Copy generated OpenVPN server data to another directory."""
    env_dir = args.root / ENVS_DIR / args.env
    return openvpn.copy_server(args=Namespace(
        cadir=env_dir / 'openvpn' / 'cadir',
        target=env_dir / 'openvpn' / 'servers' / 'current',
        **args.__dict__,
    ))


@apps.with_prog('make-ovpn')
@apps.with_help('make .ovpn file')
@with_argument_env
@apps.with_argument('config', help='provide config file name')
@apps.with_argument('client', help='provide client name')
def make_ovpn(args):
    """Make .ovpn file."""
    env_dir = args.root / ENVS_DIR / args.env
    clients = env_dir / 'openvpn' / 'clients'
    return openvpn.make_ovpn(args=Namespace(
        server_dir=env_dir / 'openvpn' / 'servers' / 'current',
        client_dir=clients,
        output=clients / (args.client + '.ovpn'),
        **args.__dict__,
    ))


@apps.with_help('manage ops environments')
@with_argument_root
@apps.with_apps(
    'operation', 'operation on environment',
    list_envs,
    generate,
    generate_user_data,
    copy_client,
    copy_server,
    make_ovpn,
)
def envs(args):
    """Manage ops environments."""
    return args.operation(args)
