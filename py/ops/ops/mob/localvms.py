__all__ = [
    'localvms',
]

from pathlib import Path
import logging
import re
import time

from garage import cli, scripts
from garage.components import ARGS


LOG = logging.getLogger(__name__)


@cli.command(help='create virtual machine')
@cli.argument(
    '--virtual-machines-dir', required=True, type=Path,
    help='provide path to VirtualBox virtual machines directory',
)
@cli.argument(
    '--name', required=True,
    help='set virtual machine name',
)
@cli.argument(
    '--image', required=True, type=Path,
    help='''provide path to virtual machine image to copy from (probably
            in VMDK format)
         ''',
)
@cli.argument(
    '--seed', required=True, type=Path,
    help='provide path to ISO image of cloud-init user data',
)
@cli.argument(
    '--ip-address', required=True,
    help='''provide the IP address of host-only interface (this should
            match the IP address recorded in the seed)
         ''',
)
def create(args: ARGS):
    """Create virtual machine and initialize it with cloud-init."""

    scripts.ensure_file(args.image)
    scripts.ensure_file(args.seed)

    # We need VDI image because when VirtualBox boots on an VMDK image,
    # Linux kernel will report **lots** of ATA error and remount root
    # file system in read-only mode.  (I don't know why, but I hope this
    # will be fixed in future version of VirtualBox.)
    image_path = (
        args.virtual_machines_dir / args.name /
        args.image.with_suffix('.vdi').name
    )
    if image_path.exists():
        LOG.error('attempt to overwrite %s', image_path)
        return 1

    LOG.info('create virtual machine')
    scripts.execute([
        'vboxmanage', 'createvm',
        '--name', args.name,
        '--ostype', 'Ubuntu_64',
        '--register',
    ])
    scripts.execute([
        'vboxmanage', 'modifyvm', args.name,
        '--memory', '512',
        '--boot1', 'disk',
        '--nic1', 'nat',
        # Enable host-only network
        '--nic2', 'hostonly',
        '--hostonlyadapter2', 'vboxnet0',
        # Enable COM1, otherwise Linux kernel will be stuck at:
        #   random: nonblocking pool is initialized
        # (I hope this is fixed in future version of VirtualBox.)
        '--uart1', '0x3f8', '4',
        '--uartmode1', 'disconnected',
    ])
    # Add IDE for the seed image
    scripts.execute([
        'vboxmanage', 'storagectl', args.name,
        '--name', 'IDE',
        '--add', 'ide',
    ])
    # Add SATA for the virtual machine image
    scripts.execute([
        'vboxmanage', 'storagectl', args.name,
        '--name', 'SATA',
        '--add', 'sata',
    ])

    LOG.info('copy virtual machine image')
    scripts.execute([
        'vboxmanage', 'clonemedium', 'disk', args.image, image_path,
        '--format', 'VDI',
    ])
    scripts.execute([
        'vboxmanage', 'storageattach', args.name,
        '--storagectl', 'SATA',
        '--port', '0',
        '--device', '0',
        '--type', 'hdd',
        '--medium', image_path,
    ])

    LOG.info('attach seed image')
    # NOTE: It looks like if you remove the seed image, cloud-init will
    # not function properly and you will not be able to login.  (This is
    # slightly annoying that you cannot later remove the seed image
    # because it is now part of the snapshot.)
    scripts.execute([
        'vboxmanage', 'storageattach', args.name,
        '--storagectl', 'IDE',
        '--port', '0',
        '--device', '0',
        '--type', 'dvddrive',
        '--medium', args.seed,
    ])

    scripts.execute([
        'vboxmanage', 'snapshot', args.name, 'take', 'created',
    ])

    LOG.info('initialize virtual machine')
    okay = True
    scripts.execute([
        'vboxmanage', 'startvm', args.name, '--type', 'headless',
    ])
    if not wait_for_vm_bootstrapping(args.name, args.ip_address):
        okay = False
    scripts.execute([
        'vboxmanage', 'controlvm', args.name, 'acpipowerbutton',
    ])
    if not wait_for_vm_poweroff(args.name):
        okay = False

    if okay:
        scripts.execute([
            'vboxmanage', 'snapshot', args.name, 'take', 'initialized',
        ])

    return 0 if okay else 1


def wait_for_vm_bootstrapping(name, ip_address):
    LOG.info('wait for virtual machine bootstrapping')
    cmd = ['ping', '-c', 1, ip_address]
    # Err out after 60 failed pings
    for _ in range(60):
        if scripts.execute(cmd, check=False).returncode == 0:
            return True
    LOG.error('virtual machine %s is not responding to ping', name)
    return False


def wait_for_vm_poweroff(name):
    LOG.info('wait for virtual machine powering off')
    # Could we not be polling vm state?
    pattern = re.compile(br'State:\s*powered off')
    cmd = ['vboxmanage', 'showvminfo', name]
    for _ in range(60):
        stdout = scripts.execute(cmd, capture_stdout=True).stdout
        if pattern.search(stdout):
            return True
        time.sleep(1)
    LOG.error('virtual machine %s is not powered off', name)
    return False


@cli.command('local-vms', help='manage local virtual machines')
@cli.sub_command_info('operation', 'operation on virtual machines')
@cli.sub_command(create)
def localvms(args: ARGS):
    """Manage local virtual machines."""
    return args.operation()
