"""Build V8 from source."""

import os

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


@decorate_rule('//shipyard:build')
def build(parameters):
    """Build V8 from source."""

    install_packages(parameters['deps'])

    depot_tools = parameters['//shipyard:build_src'] / 'depot_tools'
    git_clone(parameters['depot_tools'], depot_tools)
    path = os.environ.get('PATH')
    path = '%s:%s' % (depot_tools, path) if path else str(depot_tools)
    os.environ['PATH'] = path

    src_path = get_src_path(parameters)
    if not src_path.exists():
        call(['fetch', 'v8'], cwd=str(src_path.parent))

    if not (get_lib_path(parameters) / 'libv8.so').exists():
        call(['make', 'library=shared', parameters['target']],
             cwd=str(src_path))


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: (
     ensure_directory(get_dst_path(ps)),
     copy(ps),
 ))
 .depend('build')
 .reverse_depend('//shipyard:final_tapeout')
)


def get_src_path(parameters):
    return parameters['//shipyard:build_src'] / 'v8'


def get_lib_path(parameters):
    return (get_src_path(parameters) /
            ('out/%s/lib.target' % parameters['target']))


def get_dst_path(parameters):
    return parameters['//shipyard:build_rootfs'] / 'usr/local/lib'


def copy(parameters):
    rsync(list(get_lib_path(parameters).glob('*')), get_dst_path(parameters),
          sudo=True)
