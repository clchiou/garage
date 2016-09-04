"""Add py/buildtools to PYTHONPATH."""

from foreman import decorate_rule
from shipyard import (
    copy_source,
    ensure_file,
    insert_path,
)


@decorate_rule('//base:build')
def install(parameters):
    src = parameters['//base:root'] / 'py/buildtools'
    host_src = parameters['//base:build']  / 'host/buildtools'
    copy_source(src, host_src)
    ensure_file(host_src / 'setup.py')  # Sanity check.
    insert_path(host_src, path_variable='PYTHONPATH')
