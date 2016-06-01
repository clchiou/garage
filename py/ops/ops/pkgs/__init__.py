"""Manage packages that will not be installed from OS package manager."""

import argparse
import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from ops import scripting


LOG = logging.getLogger(__name__)


### Package: docker2aci


DOCKER2ACI_URI = 'https://github.com/appc/docker2aci/releases/download/v{version}/docker2aci-v{version}.tar.gz'


def docker2aci_install(version, tarball_path=None):
    if Path('/usr/bin/docker2aci').exists():
        LOG.warning('attempt to overwrite /usr/bin/docker2aci')
    cmds = []
    if not tarball_path:
        tarball_path = 'docker2aci.tar.gz'
        uri = DOCKER2ACI_URI.format(version=version)
        cmds.append(make_wget(uri, tarball_path))
    cmds.append(make_tar_extract(tarball_path))
    cmds.append(['sudo', 'cp', 'docker2aci', '/usr/bin'])
    with TemporaryDirectory() as working_dir:
        scripting.execute_many(cmds, cwd=working_dir)


### Package: rkt


RKT_URI = 'https://github.com/coreos/rkt/releases/download/v{version}/rkt-v{version}.tar.gz'
RKT_STAGE1_PREFIX = 'coreos.com/rkt/stage1-coreos'


def rkt_install(version, tarball_path=None):
    if Path('/usr/bin/rkt').exists():
        LOG.warning('attempt to overwrite /usr/bin/rkt')
    cmds = []
    if not tarball_path:
        tarball_path = 'rkt.tar.gz'
        cmds.append(make_wget(RKT_URI.format(version=version), tarball_path))
    # TODO: Install systemd unit files (for GC, etc.).
    cmds.extend([
        make_tar_extract(tarball_path),
        ['sudo', './scripts/setup-data-dir.sh'],
        ['sudo', './rkt', 'trust',
         '--trust-keys-from-https',
         '--prefix', RKT_STAGE1_PREFIX],
        ['sudo', './rkt', 'fetch', '%s:%s' % (RKT_STAGE1_PREFIX, version)],
        # Install rkt only if everything is okay.
        ['sudo', 'cp', 'rkt', '/usr/bin'],
    ])
    with TemporaryDirectory() as working_dir:
        scripting.execute_many(cmds, cwd=working_dir)


### Main function.


PACKAGES = {
    'docker2aci': {
        'install': docker2aci_install,
    },
    'rkt': {
        'install': rkt_install,
    },
}


def main(argv):
    parser = argparse.ArgumentParser(prog=__name__, description=__doc__)
    subparsers = parser.add_subparsers(help="""Sub-commands.""")
    # http://bugs.python.org/issue9253
    subparsers.dest = 'command'
    subparsers.required = True

    parser_install = subparsers.add_parser(
        'install', help="""Install package.""")
    parser_install.set_defaults(command=command_install)
    command_install_add_arguments(parser_install)

    args = parser.parse_args(argv[1:])
    return args.command(parser, args)


### Command: Install


def command_install_add_arguments(parser):
    scripting.add_arguments(parser)
    parser.add_argument(
        '--tarball', help="""use local tarball file for package""")
    parser.add_argument(
        'package', help="""package name of the form 'name:version'""")


def command_install(parser, args):
    scripting.process_arguments(parser, args)
    if args.tarball:
        tarball_path = Path(args.tarball).resolve()
        if not tarball_path.exists():
            raise FileNotFoundError(str(tarball_path))
    else:
        tarball_path = None

    name, version = args.package.rsplit(':', maxsplit=1)
    if name not in PACKAGES:
        raise RuntimeError('unknown package: %s' % name)
    installer = PACKAGES[name].get('install')
    if installer is None:
        raise RuntimeError('no installer for package: %s' % name)

    LOG.info('install: %s', args.package)
    installer(version, tarball_path=tarball_path)

    return 0


### Helpers


def make_wget(uri, output_path):
    # No progress bar.
    return ['wget', '--no-verbose', '--output-document', output_path, uri]


def make_tar_extract(tarball_path):
    cmd = ['tar', '--extract', '--gzip', '--strip-components', '1', '--file']
    cmd.append(tarball_path)
    return cmd
