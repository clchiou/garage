"""Common parts of the shipyard."""

import logging
from pathlib import Path

import shipyard as shipyard_
from foreman import define_parameter, decorate_rule
from shipyard import (
    call,
    ensure_directory,
    get_home,
    sync_files,
)


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


(define_parameter('root')
 .with_doc("""Location of this repository.""")
 .with_type(Path)
 .with_default(Path(shipyard_.__file__).parent.parent.parent)
)


(define_parameter('build_src')
 .with_doc("""Location of checked-out source repos.""")
 .with_type(Path)
 .with_default(get_home() / 'build/src')
)


(define_parameter('build_out')
 .with_doc("""Location of intermediate and final build artifacts.""")
 .with_type(Path)
 .with_default(get_home() / 'build/out')
)
(define_parameter('build_rootfs')
 .with_doc("""Location of final container image.""")
 .with_type(Path)
 .with_default(get_home() / 'build/out/rootfs')
)


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
    cli_tools = [
        'git',  # shipyard.git_clone()
        'rsync',  # shipyard.sync_files()
        'wget',  # shipyard.wget()
    ]
    call(['sudo', 'apt-get', 'install', '--yes'] + cli_tools)


# NOTE: All `tapeout` rules should reverse depend on this rule (or
# another `final_tapeout` rule that reverse depend on this rule).
@decorate_rule('build')
def final_tapeout(parameters):
    """Join point of all `tapeout` rules."""

    # Copy runtime libraries.
    libs = [
        '/lib/x86_64-linux-gnu',
        '/lib64',
    ]
    sync_files(libs, parameters['build_rootfs'], sudo=True)
