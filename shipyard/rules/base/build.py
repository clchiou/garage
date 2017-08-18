"""Base of all build rules."""

from pathlib import Path

from garage import scripts

from foreman import define_parameter, rule, to_path


(define_parameter.path_typed('root')
 .with_doc('Path to the root directory of this repository.')
 .with_default(Path(__file__).parent.parent.parent.parent))


(define_parameter.path_typed('drydock')
 .with_doc('Path to the directory for intermediate build artifacts.')
 .with_default(Path.home() / 'drydock'))


(define_parameter.path_typed('output')
 .with_doc('Path to the directory for final build artifacts.')
 .with_default(Path.home() / 'output'))


(define_parameter.bool_typed('release')
 .with_doc('Enable release mode for builds.')
 .with_default(True))


# Handy derived parameters
(define_parameter.path_typed('drydock/build')
 .with_doc('Path to the directory of unarchived image contents.')
 .with_derive(lambda ps: ps['drydock'] / 'build'))
(define_parameter.path_typed('drydock/manifest')
 .with_doc('Path to the image manifest.')
 .with_derive(lambda ps: ps['drydock/build'] / 'manifest'))
(define_parameter.path_typed('drydock/rootfs')
 .with_doc('Path to the image rootfs.')
 .with_derive(lambda ps: ps['drydock/build'] / 'rootfs'))


@rule
def upgrade_system(parameters):
    """Upgrade system packages."""
    with scripts.using_sudo():
        scripts.apt_get_update()
        scripts.apt_get_full_upgrade()


@rule
@rule.depend('upgrade_system', when=lambda ps: ps['release'])
def build(parameters):
    """Prepare for the build process.

       NOTE: All `build` rules should depend on this rule.
    """

    # Sanity check.
    scripts.ensure_directory(parameters['root'] / '.git')

    scripts.install_dependencies()

    # Populate drydock.
    for subdir in ('cc', 'host', 'java', 'py'):
        scripts.mkdir(parameters['drydock'] / subdir)
    scripts.mkdir(parameters['drydock/build'])
    scripts.mkdir(parameters['drydock/rootfs'])

    # Populate output (unfortunately `output` could accidentally be
    # owned by root for a variety of reasons, and we have to change it
    # back).
    with scripts.using_sudo():
        scripts.execute([
            'chown',
            '--recursive', 'plumber:plumber',
            parameters['output'],
        ])


@rule
@rule.depend('build')
def tapeout(parameters):
    """Tape-out the base system.

    NOTE: All `tapeout` rules should reverse depend on this rule.
    """
    with scripts.using_sudo():
        rootfs = parameters['drydock/rootfs']
        scripts.rsync([to_path('etc')], rootfs)
        scripts.rsync(['/lib/x86_64-linux-gnu', '/lib64'],
                      rootfs, relative=True)
        # Tapeout the entire /usr/lib/x86_64-linux-gnu might be an
        # overkill, but it's kind hard to cherry-pick just what I need
        scripts.rsync(['/usr/lib/x86_64-linux-gnu'],
                      rootfs, relative=True,
                      excludes=['/usr/lib/x86_64-linux-gnu/perl*'])
        # Tapeout only shared libraries under /usr/local/lib, which
        # excludes Python modules (if you also want to tapeout /usr/lib,
        # remember to only tapeout shared libraries under it)
        scripts.rsync(Path('/usr/local/lib').glob('lib*.so*'),
                      rootfs, relative=True)
        scripts.execute(['chown', '--recursive', 'root:root', rootfs / 'etc'])
        scripts.execute(['chmod', '--recursive', 'go-w', rootfs / 'etc'])
