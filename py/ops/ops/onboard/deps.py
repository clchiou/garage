__all__ = [
    'deps',
]

import collections
import logging
import urllib.parse
from pathlib import Path
from tempfile import TemporaryDirectory

from garage import apps
from garage import scripts


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
    version='1.29.0',
    uri='https://github.com/rkt/rkt/releases/download/v1.29.0/rkt-v1.29.0.tar.gz',
    checksum='sha512-80d669b97f5739e5d594828ff3d0a02db59dadd179b90a0f192b24fdabf14709d96329c3d09a8b4fc3f3e07874f551f48118e0b62400e53e5df2b8c574e7a841',
    strip_components=1,
)
def rkt(package):
    if Path('/usr/bin/rkt').exists():
        LOG.warning('attempt to overwrite /usr/bin/rkt')
    cmds = [
        # Don't install api and metadata service for now.
        'cp init/systemd/rkt-gc.service /lib/systemd/system'.split(),
        'cp init/systemd/rkt-gc.timer /lib/systemd/system'.split(),
        'cp init/systemd/tmpfiles.d/rkt.conf /usr/lib/tmpfiles.d'.split(),
        './scripts/setup-data-dir.sh'.split(),
        # Install rkt only if everything above succeeds.
        'cp rkt /usr/bin'.split(),
        # Fetch stage 1.
        ['rkt', 'trust',
         '--prefix', 'coreos.com/rkt/stage1-coreos',
         '--skip-fingerprint-review'],
        ['rkt', 'fetch', 'coreos.com/rkt/stage1-coreos:' + package.version],
    ]
    with scripts.using_sudo():
        for cmd in cmds:
            scripts.execute(cmd)
        scripts.systemctl_enable('rkt-gc.timer')
        scripts.systemctl_start('rkt-gc.timer')


@apps.with_prog('list')
@apps.with_help('list supported external packages')
def list_(_):
    """List supported external packages."""
    for package_name in sorted(PACKAGES):
        package = PACKAGES[package_name]
        print('%s:%s' % (package_name, package.version))
    return 0


@apps.with_help('install external package')
@apps.with_argument(
    '--tarball', metavar='PATH',
    help='use local tarball instead',
)
@apps.with_argument(
    'package',
    help='choose package (format: "name:version")',
)
def install(args):
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


@apps.with_help('manage external dependencies')
@apps.with_defaults(no_locking_required=True)
@apps.with_apps(
    'operation', 'operation on external dependencies',
    list_,
    install,
)
def deps(args):
    """\
    Manage external dependencies that will not be installed from distro
    package manager.
    """
    return args.operation(args)
