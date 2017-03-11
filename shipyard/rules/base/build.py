"""Base of all build rules."""

from pathlib import Path

from garage import scripts

from foreman import define_parameter, rule, to_path


(define_parameter('root')
 .with_doc('Path to the root directory of this repository.')
 .with_type(Path)
 .with_default(Path(__file__).parent.parent.parent.parent))


(define_parameter('drydock')
 .with_doc('Path to the directory for intermediate build artifacts.')
 .with_type(Path)
 .with_default(Path.home() / 'drydock'))


(define_parameter('output')
 .with_doc('Path to the directory for final build artifacts.')
 .with_type(Path)
 .with_default(Path.home() / 'output'))


(define_parameter('skip_system_upgrade')
 .with_doc('Whether to skip system upgrade before build starts.')
 .with_type(bool)
 .with_default(False)
 .with_parse(lambda v: v.lower() == 'true'))


# Handy derived parameters
(define_parameter('drydock/image')
 .with_doc('Path to the directory of unarchived image contents.')
 .with_type(Path)
 .with_derive(lambda ps: ps['drydock'] / 'build'))
(define_parameter('drydock/manifest')
 .with_doc('Path to the image manifest.')
 .with_type(Path)
 .with_derive(lambda ps: ps['drydock/image'] / 'manifest'))
(define_parameter('drydock/rootfs')
 .with_doc('Path to the image rootfs.')
 .with_type(Path)
 .with_derive(lambda ps: ps['drydock/image'] / 'rootfs'))


@rule
def system_upgrade(parameters):
    """Upgrade system packages."""
    with scripts.using_sudo():
        scripts.apt_get_update()
        scripts.apt_get_full_upgrade()


@rule.depend('system_upgrade', when=lambda ps: not ps['skip_system_upgrade'])
def base(parameters):
    """Prepare system for build process."""
    scripts.install_dependencies()


@rule.depend('base')
def build(parameters):
    """Prepare for the build process.

       NOTE: All `build` rules should depend on this rule.
    """

    # Sanity check
    scripts.ensure_directory(parameters['root'] / '.git')

    # Populate drydock
    for subdir in ('cc', 'host', 'java', 'py'):
        scripts.mkdir(parameters['drydock'] / subdir)
    scripts.mkdir(parameters['drydock/image'])
    scripts.mkdir(parameters['drydock/rootfs'])


@rule.depend('build')
def tapeout(parameters):
    """Tape-out the base system.

       NOTE: All `tapeout` rules should reverse depend on this rule.
    """
    rootfs = parameters['drydock/rootfs']
    libs = ['/lib/x86_64-linux-gnu', '/lib64']
    with scripts.using_sudo():
        scripts.rsync([to_path('etc')], rootfs)
        scripts.rsync(libs, rootfs, relative=True)
        scripts.execute(['chown', '--recursive', 'root:root', rootfs / 'etc'])
        scripts.execute(['chmod', '--recursive', 'go-w', rootfs / 'etc'])
