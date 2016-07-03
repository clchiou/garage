"""Build V8 Python binding."""

import os

from foreman import define_rule, decorate_rule
from shipyard import (
    copy_source,
    ensure_file,
)
from shipyard import py


@decorate_rule('//base:build',
               '//cpython:build',
               '//cpython:install_cython',
               '//v8:build')
def build(parameters):
    """Build V8 Python binding."""

    build_src = parameters['//base:build_src'] / 'py/v8'
    copy_source(parameters['//base:root'] / 'py/v8', build_src)
    ensure_file(build_src / 'setup.py')  # Sanity check.

    v8_build_src = parameters['//v8:build_src']
    if not v8_build_src.is_dir():
        raise FileExistsError('not a directory: %s' % v8_build_src)
    os.environ['V8'] = str(v8_build_src)

    v8_out = parameters['//v8:out_target']
    if not v8_out.is_dir():
        raise FileExistsError('not a directory: %s' % v8_out)
    os.environ['V8_OUT'] = str(v8_out)

    # Remove v8/data/*.bin so that setup.py would create link to the
    # latest blobs.
    for filename in ('natives_blob.bin', 'snapshot_blob.bin'):
        blob_path = build_src / 'v8/data' / filename
        # NOTE: Path.exists() returns False on failed symlink.
        if blob_path.exists() or blob_path.is_symlink():
            blob_path.unlink()

    py.build_package(parameters, 'v8', build_src)


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: py.tapeout_package(ps, 'v8'))
 .depend('build')
 .depend('//v8:tapeout')
 .reverse_depend('//base:tapeout')
 .reverse_depend('//cpython:tapeout')
)
