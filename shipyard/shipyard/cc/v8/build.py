"""Build V8 from source."""

import logging
import os
from pathlib import Path

from foreman import define_parameter, define_rule, decorate_rule
from shipyard import (

    ensure_directory,
    execute,
    git_clone,
    rsync,

    install_packages,
)


LOG = logging.getLogger(__name__)


# NOTE: Use top of trunk at the moment.
(define_parameter('repo')
 .with_doc("""Location of source repo.""")
 .with_type(str)
 .with_default('https://chromium.googlesource.com/v8/v8.git')
)


(define_parameter('depot_tools')
 .with_doc("""Location of depot_tools.""")
 .with_type(str)
 .with_default(
     'https://chromium.googlesource.com/chromium/tools/depot_tools.git')
)


(define_parameter('deps')
 .with_doc("""Build-time Debian packages.""")
 .with_type(list)
 .with_parse(lambda pkgs: pkgs.split(','))
 .with_default([
     'build-essential',  # GCC and make.
     'python',  # depot_tools needs Python 2.
 ])
)


(define_parameter('target')
 .with_doc("""Build target.""")
 .with_type(str)
 .with_default('x64.release')
)


(define_parameter('build_src')
 .with_type(Path)
 .with_derive(lambda ps: ps['//base:build'] / 'cc/v8')
)
(define_parameter('out_target')
 .with_type(Path)
 .with_derive(
     lambda ps: ps['build_src'] / ('out/%s' % ps['target']))
)


@decorate_rule('//base:build')
def build(parameters):
    """Build V8 from source."""

    install_packages(parameters['deps'])

    depot_tools = parameters['//base:build'] / 'host/depot_tools'
    git_clone(parameters['depot_tools'], depot_tools)
    path = os.environ.get('PATH')
    path = '%s:%s' % (depot_tools, path) if path else str(depot_tools)
    os.environ['PATH'] = path

    build_src = parameters['build_src']
    if not build_src.exists():
        LOG.info('fetch V8')
        execute(['fetch', 'v8'], cwd=build_src.parent)

    fix_gold_version(parameters)

    if not (parameters['out_target'] / 'lib.target/libv8.so').exists():
        LOG.info('build V8')
        execute(['make', 'library=shared', parameters['target']],
                cwd=build_src)


def fix_gold_version(parameters):
    """Replace gold that is bundled with V8 if it's too old (which will
       cause build break).
    """

    old_version = b'GNU Binutils 2.24'

    gold = (parameters['build_src'] /
            'third_party/binutils/Linux_x64/Release/bin/ld.gold')
    if not gold.exists():
        return

    if old_version not in execute([gold, '--version'], return_output=True):
        return

    new_gold = execute(['which', 'gold'], return_output=True)
    new_gold = Path(new_gold.decode('ascii').strip())
    if old_version in execute([new_gold, '--version'], return_output=True):
        raise RuntimeError('gold version too old')

    LOG.info('replace bundled gold with: %s', new_gold)
    gold.rename(gold.with_suffix('.bak'))
    gold.symlink_to(new_gold)


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: (
     ensure_directory(ps['//base:build_rootfs'] / 'usr/local/lib'),
     rsync(list((ps['out_target'] / 'lib.target').glob('*')),
           ps['//base:build_rootfs'] / 'usr/local/lib',
           sudo=True),
 ))
 .depend('build')
 .reverse_depend('//base:tapeout')
)
