"""Build V8 from source."""

import os
from pathlib import Path

from foreman import define_parameter, define_rule, decorate_rule
from shipyard import (

    call,
    ensure_directory,
    git_clone,
    rsync,

    install_packages,
)


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
     # GCC and make.
     'build-essential',
 ])
)


(define_parameter('target')
 .with_doc("""Build target.""")
 .with_type(str)
 .with_default('x64.release')
)


(define_parameter('build_src')
 .with_type(Path)
 .with_derive(lambda ps: ps['//shipyard:build_src'] / 'v8')
)
(define_parameter('out_target')
 .with_type(Path)
 .with_derive(
     lambda ps: ps['build_src'] / ('out/%s' % ps['target']))
)


@decorate_rule('//shipyard:build')
def build(parameters):
    """Build V8 from source."""

    install_packages(parameters['deps'])

    depot_tools = parameters['//shipyard:build_src'] / 'depot_tools'
    git_clone(parameters['depot_tools'], depot_tools)
    path = os.environ.get('PATH')
    path = '%s:%s' % (depot_tools, path) if path else str(depot_tools)
    os.environ['PATH'] = path

    build_src = parameters['build_src']
    if not build_src.exists():
        call(['fetch', 'v8'], cwd=str(build_src.parent))

    if not (parameters['out_target'] / 'lib.target/libv8.so').exists():
        call(['make', 'library=shared', parameters['target']],
             cwd=str(build_src))


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: (
     ensure_directory(ps['//shipyard:build_rootfs'] / 'usr/local/lib'),
     rsync(list((ps['out_target'] / 'lib.target').glob('*')),
           ps['//shipyard:build_rootfs'] / 'usr/local/lib',
           sudo=True),
 ))
 .depend('build')
 .reverse_depend('//shipyard:final_tapeout')
)
