"""Build V8 Python binding."""

from foreman import define_rule, decorate_rule
from shipyard import (
    copy_source,
    ensure_file,
)
from shipyard import py


@decorate_rule('//base:build',
               '//cc/v8:build',
               '//py/cpython:build',
               '//py/cpython:install_cython')
def build(parameters):
    """Build V8 Python binding."""

    build_src = parameters['//base:build'] / 'py/v8'
    copy_source(parameters['//base:root'] / 'py/v8', build_src)
    ensure_file(build_src / 'setup.py')  # Sanity check.

    v8_build_src = parameters['//cc/v8:build_src']
    if not v8_build_src.is_dir():
        raise FileExistsError('not a directory: %s' % v8_build_src)

    # Add v8_build_src to include directories to workaround a bug(?) in
    # libplatform/libplatform.h (which should be fixed pretty soon?).
    include_dirs = '{v8_build_src}:{v8_build_src}/include'.format(
        v8_build_src=v8_build_src)

    v8_out = parameters['//cc/v8:out_target']
    if not v8_out.is_dir():
        raise FileExistsError('not a directory: %s' % v8_out)

    library_dirs = (
        '{v8_out}/lib.target:{v8_out}/obj.target/src'.format(v8_out=v8_out))

    build_cmd = ['build']
    build_cmd.extend(['copy_v8_data', '--v8-out', v8_out])
    build_cmd.extend([
        'build_ext',
        '--include-dirs', include_dirs,
        '--library-dirs', library_dirs,
    ])

    py.build_package(parameters, 'v8', build_src, build_cmd=build_cmd)


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: py.tapeout_package(ps, 'v8'))
 .depend('build')
 .depend('//cc/v8:tapeout')
 .reverse_depend('//base:tapeout')
 .reverse_depend('//py/cpython:tapeout')
)
