__all__ = [
    'cloudinit',
]

from pathlib import Path
import logging

import yaml

from garage import asserts, cli, scripts
from garage.components import ARGS

from . import keys


LOG = logging.getLogger(__name__)


@cli.command('gen-user-data', help='generate user data')
@cli.argument(
    '--ssh-host-key',
    nargs=3, metavar=('ALGORITHM', 'PRIVATE_KEY', 'PUBLIC_KEY'),
    action='append', required=True,
    help='add SSH host key for authenticating server',
)
@cli.argument(
    '--ssh-authorized-key',
    metavar='PATH', type=Path, action='append', required=True,
    help='add SSH authorized key for authenticating client',
)
@cli.argument(
    '--local-vm',
    nargs=4, metavar=('HOSTNAME', 'FQDN', 'INTERFACE', 'IP_ADDRESS'),
    help='''set additional data for local VirtualBox machine, which
            are: hostname, FQDN, host-only network interface, and
            its IP address
         '''
)
@cli.argument(
    'output', type=Path,
    help='set output YAML file path',
)
def generate_user_data(args: ARGS):
    """Generate cloud-init user data.

       SSH host key is a tuple of algorithm, private key file, and
       public key file.  "algorithm" is what you chose when generating
       the key pair, and should be one of dsa, ecdsa, ed25519, or rsa.

       SSH authorized key is your public key for password-less login.
    """

    templates_dir = Path(__file__).parent / 'templates'

    user_data = yaml.load((templates_dir / 'user-data.yaml').read_text())

    key_algorithms = frozenset(algo for algo, _ in keys.HOST_KEYS)

    # Insert `ssh_keys`
    ssh_keys = user_data['ssh_keys']
    for algorithm, private_key, public_key in args.ssh_host_key:
        if algorithm not in key_algorithms:
            LOG.error('unsupported ssh key algorithm: %s', algorithm)
            return 1
        private_key = scripts.ensure_file(private_key)
        public_key = scripts.ensure_file(public_key)
        # Just a sanity check
        if private_key.suffix != '':
            LOG.warning('private key file has suffix: %s', private_key)
        if public_key.suffix != '.pub':
            LOG.warning('public key file suffix not .pub: %s', public_key)
        ssh_keys.update({
            ('%s_private' % algorithm): private_key.read_text(),
            ('%s_public' % algorithm): public_key.read_text(),
        })

    # Insert `ssh-authorized-keys` to account plumber
    asserts.precond(len(user_data['users']) == 1)
    plumber = user_data['users'][0]
    asserts.postcond(plumber['name'] == 'plumber')
    public_keys = plumber['ssh-authorized-keys']
    for public_key in args.ssh_authorized_key:
        public_key = scripts.ensure_file(public_key)
        if public_key.suffix != '.pub':
            LOG.warning('public key file suffix not .pub: %s', public_key)
        public_keys.append(public_key.read_text())

    if args.local_vm:
        # Insert fields only for local VirtualBox virtual machine
        hostname, fqdn, interface, ip_address = args.local_vm

        user_data['hostname'] = hostname
        user_data['fqdn'] = fqdn

        # Insert host-only network configuration file
        #
        # I need this because I couldn't configure host-only network
        # interface from cloud-init metadata.  Also, note that you
        # should not set `gateway` for the host-only interface.
        cfg = (templates_dir / '99-host-only.cfg').read_text().format(
            interface=interface,
            ip_address=ip_address,
            ip_address_parts=ip_address.split('.'),
        )
        user_data.setdefault('write_files', []).append({
            'path': '/etc/network/interfaces.d/99-host-only.cfg',
            'owner': 'root:root',
            'permissions': '0644',
            'content': cfg,
        })

        # Insert `ifup ${interface}` into `runcmd`
        user_data['runcmd'].append('ifup %s' % interface)

    else:
        user_data.pop('hostname')
        user_data.pop('fqdn')

    user_data_yaml = yaml.dump(user_data)

    if args.output.exists():
        LOG.warning('attempt to overwrite: %s', args.output)
    scripts.ensure_contents(
        args.output,
        '#cloud-config\n\n' + user_data_yaml,
    )

    if args.local_vm:
        scripts.execute([
            'cloud-localds', '--verbose',
            args.output.with_suffix('.iso'),
            args.output,
        ])

    return 0


@cli.command('cloud-init', help='manage cloud-init data')
@cli.sub_command_info('operation', 'operation on cloud-init data')
@cli.sub_command(generate_user_data)
def cloudinit(args: ARGS):
    """Manage cloud-init data."""
    return args.operation()
