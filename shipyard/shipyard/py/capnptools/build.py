"""Build capnptools."""

# NOTE: You most likely would build but not tapeout this package since
# this package is only useful for generating capnp code (and so we only
# define build rule here).

from pathlib import Path

from foreman import decorate_rule, define_parameter
from shipyard import copy_source
from shipyard import ensure_file
from shipyard import py


PACKAGE_NAME = 'capnptools'
PATH = 'py/capnptools'


(define_parameter('schema')
 .with_doc("""Location of the schema.capnp file.""")
 .with_type(Path)
 .with_default(Path('/usr/local/include/capnp/schema.capnp'))
)


py.define_package_common(
    derive_src_path=lambda ps: ps['//base:root'] / PATH,
    derive_build_src_path=lambda ps: ps['//base:build'] / PATH,
)


@decorate_rule('//cc/capnproto:build',
               '//host/buildtools:install',
               '//py/cpython:install_cython',
               '//py/mako:build')
def build(parameters):
    """Build capnptools."""
    copy_source(parameters['src'], parameters['build_src'])
    ensure_file(parameters['build_src'] / 'setup.py')
    ensure_file(parameters['schema'])
    py.build_package(
        parameters,
        PACKAGE_NAME,
        parameters['build_src'],
        build_cmd=[
            'build',
            'compile_schema', '--schema', parameters['schema'],
        ],
    )
