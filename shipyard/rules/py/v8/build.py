from garage import scripts

from templates import py


def make_build_cmd(parameters):
    v8 = parameters['//base:drydock'] / 'cc/v8'
    scripts.ensure_directory(v8)  # Sanity check
    return [
        'build',
        'copy_files', '--src-dir', parameters['//cc/v8:output'],
        # Style-wise, V8 code prefers to include "include/v8.h" rather
        # than just "v8.h", but some (all?) of the headers under the
        # `include` directory are using "v8.h" style.  I don't know why
        # it's inconsistent, but let's add both to include path.
        'build_ext', '--include-dirs', '%s:%s' % (v8, v8 / 'include'),
    ]


rules = py.define_package(package='v8', make_build_cmd=make_build_cmd)
rules.build.depend('//cc/v8:build')
rules.build.depend('//host/buildtools:install')
rules.build.depend('//host/cython:install')
rules.tapeout.depend('//cc/v8:tapeout')
