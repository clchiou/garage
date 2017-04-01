__all__ = [
    'keys',
]

from pathlib import Path
import logging

from garage import cli, scripts
from garage.components import ARGS


LOG = logging.getLogger(__name__)


HOST_KEYS = [
    ('dsa', 1024),
    ('ecdsa', 521),
    ('ed25519', None),
    ('rsa', 4096),
]


# ECDSA requires less bits than RSA at same level of strength and
# thus seems to be the best choice
USER_KEY_ALGORITHM = 'ecdsa'
USER_KEY_SIZE = 521


def ssh_host_key_filename(algorithm):
    return 'ssh_host_%s_key' % algorithm


def ssh_user_key_filename(algorithm):
    return 'id_' + algorithm


@cli.command('gen-host-key', help='generate host keys')
@cli.argument('output_dir', type=Path, help='set output directory')
def generate_host_key(args: ARGS):
    """Generate SSH host keys with ssh-keygen."""

    key_paths = [
        args.output_dir / ssh_host_key_filename(algorithm)
        for algorithm, _ in HOST_KEYS
    ]
    okay = True
    for key_path in key_paths:
        if key_path.exists():
            LOG.error('attempt to overwrite %s', key_path)
            okay = False
    if not okay:
        return 1

    scripts.mkdir(args.output_dir)
    for (algorithm, key_size), key_path in zip(HOST_KEYS, key_paths):
        cmd = [
            'ssh-keygen',
            '-t', algorithm,
            '-N', '',  # No password
            '-C', 'root@localhost',
            '-f', key_path,
        ]
        if key_size:
            cmd.extend(['-b', key_size])
        scripts.execute(cmd)

    return 0


@cli.command('gen-user-key', help='generate user key pair')
@cli.argument('output_dir', type=Path, help='set output directory')
def generate_user_key(args: ARGS):
    """Generate SSH key pair with ssh-keygen."""
    key_path = args.output_dir / ssh_user_key_filename(USER_KEY_ALGORITHM)
    if key_path.exists():
        LOG.error('attempt to overwrite %s', key_path)
        return 1
    scripts.mkdir(args.output_dir)
    scripts.execute([
        'ssh-keygen',
        '-t', USER_KEY_ALGORITHM,
        '-b', USER_KEY_SIZE,
        '-C', 'plumber@localhost',
        '-f', key_path,
    ])
    return 0


@cli.command(help='manage security keys')
@cli.sub_command_info('operation', 'operation on keys')
@cli.sub_command(generate_host_key)
@cli.sub_command(generate_user_key)
def keys(args: ARGS):
    """Manage security keys."""
    return args.operation()
