"""Install packages that will not be installed from OS package manager."""

import argparse
import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from ops.common import commands


LOG = logging.getLogger(__name__)


### Package: rkt


RKT_URI = 'https://github.com/coreos/rkt/releases/download/v{version}/rkt-v{version}.tar.gz'
RKT_STAGE1_PREFIX = 'coreos.com/rkt/stage1-coreos'


def install_rkt(version, tarball_path=None):
    if Path('/usr/bin/rkt').exists():
        LOG.warning('attempt to overwrite /usr/bin/rkt')
    cmds = []
    if not tarball_path:
        tarball_path = 'rkt.tar.gz'
        cmds.append(
            ['wget',
             '--no-verbose',  # No progress bar.
             '--output-document', tarball_path,
             RKT_URI.format(version=version)]
        )
    cmds.extend([
        ['tar',
         '--extract',
         '--gzip',
         '--strip-components', '1',
         '--file', tarball_path],
        ['sudo', './scripts/setup-data-dir.sh'],
        ['sudo', './rkt', 'trust',
         '--trust-keys-from-https',
         '--prefix', RKT_STAGE1_PREFIX],
        ['sudo', './rkt', 'fetch', '%s:%s' % (RKT_STAGE1_PREFIX, version)],
        # Install rkt only if everything is okay.
        ['sudo', 'cp', 'rkt', '/usr/bin'],
    ])
    with TemporaryDirectory() as working_dir:
        commands.execute_many(cmds, cwd=working_dir)


### Main function.


PACKAGES = {
    'rkt': install_rkt,
}


def main(argv):
    prog = __name__ if argv[0].endswith('__main__.py') else argv[0]
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    commands.add_args(parser)
    parser.add_argument(
        '--tarball', help="""use local package tarball file""")
    parser.add_argument(
        'package', help="""install package with the form 'name:version'""")

    args = parser.parse_args(argv[1:])
    commands.process_args(parser, args)
    if args.tarball:
        tarball_path = Path(args.tarball).resolve()
        if not tarball_path.exists():
            raise FileNotFoundError(str(tarball_path))
    else:
        tarball_path = None

    name, version = args.package.rsplit(':', maxsplit=1)
    if name not in PACKAGES:
        raise RuntimeError('unknown package: %s' % name)
    LOG.info('install: %s', args.package)
    PACKAGES[name](version, tarball_path=tarball_path)

    return 0
