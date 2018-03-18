__all__ = [
    'cloudinit',
]

from pathlib import Path
import logging

# Prefer ruamel.yaml over PyYAML.
try:
    from ruamel.yaml import YAML
    import io

    _YAML = YAML()

    def yaml_dump(data):
        with io.StringIO() as output:
            _YAML.dump(data, output)
            return output.getvalue()

    yaml_load = _YAML.load

except ImportError:
    import yaml
    yaml_dump = yaml.dump
    yaml_load = yaml.load

from garage import apps
from garage import scripts
from garage.assertions import ASSERT

from . import keys


LOG = logging.getLogger(__name__)


@apps.with_prog('gen-user-data')
@apps.with_help('generate user data')
@apps.with_argument(
    '--ssh-host-key',
    nargs=3, metavar=('ALGORITHM', 'PRIVATE_KEY', 'PUBLIC_KEY'),
    action='append', required=True,
    help='add SSH host key for authenticating server',
)
@apps.with_argument(
    '--ssh-authorized-key',
    metavar='PATH', type=Path, action='append', required=True,
    help='add SSH authorized key for authenticating client',
)
@apps.with_argument(
    '--local-vm',
    nargs=4, metavar=('HOSTNAME', 'FQDN', 'INTERFACE', 'IP_ADDRESS'),
    help='''set additional data for local VirtualBox machine, which
            are: hostname, FQDN, host-only network interface, and
            its IP address
         '''
)
@apps.with_argument(
    '--password',
    help='set login password, which should only be used in testing',
)
@apps.with_argument(
    'output', type=Path,
    help='set output YAML file path',
)
def generate_user_data(args):
    """Generate cloud-init user data.

    SSH host key is a tuple of algorithm, private key file, and public
    key file.  "algorithm" is what you chose when generating the key
    pair, and should be one of dsa, ecdsa, ed25519, or rsa.

    SSH authorized key is your public key for password-less login.
    """

    templates_dir = Path(__file__).parent / 'templates'

    user_data = yaml_load((templates_dir / 'user-data.yaml').read_text())

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
    ASSERT.equal(len(user_data['users']), 1)
    plumber = user_data['users'][0]
    ASSERT.equal(plumber['name'], 'plumber')
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
        cfg = (templates_dir / '99-host-only.yaml').read_text().format(
            interface=interface,
            ip_address=ip_address,
        )
        user_data.setdefault('write_files', []).append({
            'path': '/etc/netplan/99-host-only.yaml',
            'owner': 'root:root',
            'permissions': '0644',
            'content': cfg,
        })

        # Do this for the first boot in case the host-only interface is
        # not brought up.
        user_data['runcmd'].append('netplan generate')
        user_data['runcmd'].append('netplan apply')

    else:
        user_data.pop('hostname')
        user_data.pop('fqdn')

    if args.password:
        LOG.warning('use password login, which is insecure')
        user_data['chpasswd'] = {
            'list': 'plumber:%s\n' % args.password,
            'expire': False,
        }

    user_data_yaml = yaml_dump(user_data)

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


@apps.with_prog('cloud-init')
@apps.with_help('manage cloud-init data')
@apps.with_apps(
    'operation', 'operation on cloud-init data',
    generate_user_data,
)
def cloudinit(args):
    """Manage cloud-init data."""
    return args.operation(args)
