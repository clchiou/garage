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
 .with_default(Path(shipyard_.__file__).parent.parent)
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
def shipyard(parameters):
    """Common setup of the shipyard."""
    ensure_directory(parameters['build_src'])
    ensure_directory(parameters['build_out'])
    ensure_directory(parameters['build_rootfs'])
    cli_tools = [
        'rsync',  # shipyard.sync_files()
        'wget',  # shipyard.wget()
    ]
    call(['sudo', 'apt-get', 'install', '--yes'] + cli_tools)


@decorate_rule
def build_image(parameters):
    """Copy runtime libraries."""
    libs = [
        '/lib/x86_64-linux-gnu',
        '/lib64',
    ]
    sync_files(libs, parameters['build_rootfs'], sudo=True)
