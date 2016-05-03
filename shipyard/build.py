"""Common parts of the shipyard."""

import logging
import os
import os.path

from foreman import define_parameter, decorate_rule

from shipyard import (
    call,
    ensure_directory,
    sync_files,
)


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


(define_parameter('build_src')
 .with_doc("""Location of checked-out source repos.""")
 .with_type(str)
 .with_default(os.path.join(os.environ['HOME'], 'build/src'))
)


(define_parameter('build_out')
 .with_doc("""Location of intermediate and final build artifacts.""")
 .with_type(str)
 .with_default(os.path.join(os.environ['HOME'], 'build/out'))
)
(define_parameter('build_rootfs')
 .with_doc("""Location of final container image.""")
 .with_type(str)
 .with_default(os.path.join(os.environ['HOME'], 'build/out/rootfs'))
)


@decorate_rule
def shipyard(parameters):
    """Common setup of the shipyard."""
    ensure_directory(parameters['build_src'])
    ensure_directory(parameters['build_out'])
    ensure_directory(parameters['build_rootfs'])
    cli_tools = ['wget']
    call(['sudo', 'apt-get', 'install', '--yes'] + cli_tools)


@decorate_rule
def build_image(parameters):
    """Copy runtime libraries."""
    libs = [
        '/lib/x86_64-linux-gnu',
        '/lib64',
    ]
    sync_files(libs, parameters['build_rootfs'], sudo=True)
