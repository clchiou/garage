"""Base part of the application image."""

from pathlib import Path

from foreman import define_parameter, define_rule, decorate_rule, to_path
from shipyard import (
    __file__ as shipyard_path,
    ensure_directory,
    execute,
    rsync,
)


(define_parameter('root')
 .with_doc("""Location of this repository.""")
 .with_type(Path)
 .with_default(Path(shipyard_path).parent.parent.parent.parent)
)


(define_parameter('build')
 .with_doc("""Location of build artifacts.""")
 .with_type(Path)
 .with_default(Path.home() / 'build')
)


(define_parameter('image')
 .with_doc("""Location of image artifacts.""")
 .with_type(Path)
 .with_derive(lambda ps: ps['build'] / 'output')
)
(define_parameter('manifest')
 .with_doc("""Location of image manifest.""")
 .with_type(Path)
 .with_derive(lambda ps: ps['image'] / 'manifest')
)
(define_parameter('rootfs')
 .with_doc("""Location of image rootfs.""")
 .with_type(Path)
 .with_derive(lambda ps: ps['image'] / 'rootfs')
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

    ensure_directory(parameters['build'])
    ensure_directory(parameters['build'] / 'cc')
    ensure_directory(parameters['build'] / 'host')
    ensure_directory(parameters['build'] / 'java')
    ensure_directory(parameters['build'] / 'py')
    ensure_directory(parameters['image'])
    ensure_directory(parameters['rootfs'])

    if parameters['update']:
        execute(['sudo', 'apt-get', 'update'])
        execute(['sudo', 'apt-get', '--yes', 'upgrade'])

    execute([
        'sudo', 'apt-get', 'install', '--yes',
        'git',  # shipyard.git_clone()
        'rsync',  # shipyard.rsync()
        'unzip',  # shipyard.define_archive()
        'wget',  # shipyard.wget()
    ])


# NOTE: All `tapeout` rules should reverse depend on this rule.
@decorate_rule('build')
def tapeout(parameters):
    """Join point of all `tapeout` rules."""
    # Copy /etc and runtime libraries.
    rootfs = parameters['rootfs']
    libs = ['/lib/x86_64-linux-gnu', '/lib64']
    rsync([to_path('etc')], rootfs, sudo=True)
    rsync(libs, rootfs, relative=True, sudo=True)
    execute(['sudo', 'chown', '--recursive', 'root:root', rootfs / 'etc'])
