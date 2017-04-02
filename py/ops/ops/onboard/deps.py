__all__ = [
    'deps',
]

import collections
import logging
import urllib.parse
from pathlib import Path
from tempfile import TemporaryDirectory

from garage import cli, scripts
from garage.components import ARGS


LOG = logging.getLogger(__name__)


# TODO: Use typing.NamedTuple and the new annotation syntax when all
# systems are upgraded to Python 3.6
Package = collections.namedtuple('Package', [
    'name',
    # TODO: Support multiple versions
    'version',
    'uri',
    'checksum',
    'strip_components',
    'install',
])


PACKAGES = {}


def define_package(**kwargs):
    def decorate(install):
        package = Package(name=install.__name__, install=install, **kwargs)
        PACKAGES[package.name] = package
        return install
    return decorate


@define_package(
    version='1.25.0',
    uri='https://github.com/coreos/rkt/releases/download/v1.25.0/rkt-v1.25.0.tar.gz',
    checksum='sha512-6a65f51af793df4fe054dd1a8f791bcf2e30c6a15593b908515a6616835490cad03d9d927b1c88dd38b77647a9a5f9e40ffba913b92e5c2d6f141a758e0805d8',
    strip_components=1,
)
def rkt(package):
    if Path('/usr/bin/rkt').exists():
        LOG.warning('attempt to overwrite /usr/bin/rkt')
    cmds = [
        # Don't install api and metadata service for now
        'cp init/systemd/rkt-gc.service /lib/systemd/system'.split(),
        'cp init/systemd/rkt-gc.timer /lib/systemd/system'.split(),
        'cp init/systemd/tmpfiles.d/rkt.conf /usr/lib/tmpfiles.d'.split(),
        './scripts/setup-data-dir.sh'.split(),
        # Install rkt only if everything above succeeds
        'cp rkt /usr/bin'.split(),
    ]
    with scripts.using_sudo():
        for cmd in cmds:
            scripts.execute(cmd)
        scripts.systemctl_enable('rkt-gc.timer')
        scripts.systemctl_start('rkt-gc.timer')


@cli.command('list', help='list supported external packages')
def list_():
    """List supported external packages."""
    for package_name in sorted(PACKAGES):
        package = PACKAGES[package_name]
        print('%s:%s' % (package_name, package.version))
    return 0


@cli.command(help='install external package')
@cli.argument('--tarball', metavar='PATH', help='use local tarball instead')
@cli.argument('package', help='choose package (format: "name:version")')
def install(args: ARGS):
    """Install external package."""

    package_name, package_version = args.package.split(':', maxsplit=1)
    package = PACKAGES.get(package_name)
    if package is None:
        raise RuntimeError('unknown package: %s' % args.package)
    if package_version != 'latest' and package_version != package.version:
        raise RuntimeError('unsupported package version: %s' % args.package)

    with TemporaryDirectory() as staging_dir:
        staging_dir = Path(staging_dir)

        if args.tarball:
            tarball_path = scripts.ensure_file(Path(args.tarball).resolve())
        else:
            tarball_path = urllib.parse.urlparse(package.uri).path
            tarball_path = staging_dir / Path(tarball_path).name
            scripts.wget(package.uri, tarball_path)
        scripts.ensure_checksum(tarball_path, package.checksum)

        with scripts.directory(staging_dir):
            if package.strip_components > 0:
                tar_extra_flags = [
                    '--strip-components', package.strip_components,
                ]
            else:
                tar_extra_flags = []
            scripts.tar_extract(tarball_path, tar_extra_flags=tar_extra_flags)
            package.install(package)

    return 0


@cli.command(help='manage external dependencies')
@cli.defaults(no_locking_required=True)
@cli.sub_command_info('operation', 'operation on external dependencies')
@cli.sub_command(list_)
@cli.sub_command(install)
def deps(args: ARGS):
    """\
    Manage external dependencies that will not be installed from distro
    package manager.
    """
    return args.operation()
