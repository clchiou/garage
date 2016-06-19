"""Base part of the application image."""

from pathlib import Path

import shipyard as shipyard_
from foreman import define_parameter, define_rule, decorate_rule, to_path
from shipyard import (
    build_appc_image,
    call,
    ensure_directory,
    rsync,
)


(define_parameter('root')
 .with_doc("""Location of this repository.""")
 .with_type(Path)
 .with_default(Path(shipyard_.__file__).parent.parent.parent)
)


(define_parameter('build')
 .with_doc("""Location of build artifacts.""")
 .with_type(Path)
 .with_default(Path.home() / 'build')
)


(define_parameter('build_src')
 .with_doc("""Location of checked-out source repos.""")
 .with_type(Path)
 .with_default(Path.home() / 'build/src')
)


(define_parameter('build_out')
 .with_doc("""Location of intermediate and final build artifacts.""")
 .with_type(Path)
 .with_default(Path.home() / 'build/out')
)
(define_parameter('build_rootfs')
 .with_doc("""Location of final container image data.""")
 .with_type(Path)
 .with_default(Path.home() / 'build/out/rootfs')
)


(define_parameter('output')
 .with_doc("""Location of final build artifacts.""")
 .with_type(Path)
 .with_default(Path.home() / 'output')
)


(define_parameter('update')
 .with_doc("""Whether to update OS package index.""")
 .with_type(bool)
 .with_parse(lambda update: update.lower() == 'true')
 .with_default(True)
)


# NOTE: All `build` rule should depend on this rule.
@decorate_rule
def build(parameters):
    """Common setup of the shipyard."""

    # Sanity check
    git_dir = parameters['root'] / '.git'
    if not git_dir.is_dir():
        raise FileExistsError('not a directory: %s' % git_dir)

    ensure_directory(parameters['build_src'])
    ensure_directory(parameters['build_out'])
    ensure_directory(parameters['build_rootfs'])

    if parameters['update']:
        call(['sudo', 'apt-get', 'update'])
        call(['sudo', 'apt-get', '--yes', 'upgrade'])

    call([
        'sudo', 'apt-get', 'install', '--yes',
        'git',  # shipyard.git_clone()
        'rsync',  # shipyard.rsync()
        'wget',  # shipyard.wget()
    ])


# NOTE: All `tapeout` rules should reverse depend on this rule.
@decorate_rule('build')
def tapeout(parameters):
    """Join point of all `tapeout` rules."""
    # Copy /etc and runtime libraries.
    rootfs = parameters['build_rootfs']
    libs = ['/lib/x86_64-linux-gnu', '/lib64']
    rsync([to_path('etc')], rootfs, sudo=True)
    rsync(libs, rootfs, relative=True, sudo=True)
    call(['sudo', 'chown', '--recursive', 'root:root', str(rootfs / 'etc')])


(define_rule('build_image')
 .with_doc("""Build containerized image.""")
 .with_build(lambda ps: build_appc_image(ps['build_out'], ps['output']))
 .depend('tapeout')
)
