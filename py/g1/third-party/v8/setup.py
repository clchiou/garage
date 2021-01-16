import sys
from distutils.command.build import build
from setuptools import setup
from setuptools.extension import Extension

from g1.devtools import buildtools

#
# V8 does not provide a pkg-config .pc file from which we can extract
# the include and library directory path; so you must add the paths to
# commands manually:
#   copy_files --src-dir=..
#   build_ext --include-dirs=... --library-dirs=...
#
# This applies to Boost as well if it is not installed at a standard
# location like /usr/local.
#
setup(
    name='v8',
    cmdclass={
        cmd.__name__: cmd
        for cmd in buildtools.register_subcommands(
            build,
            buildtools.make_copy_files(
                filenames=['icudtl.dat'],
                dst_dir='v8',
            ),
        )
    },
    packages=[
        'v8',
    ],
    package_data={
        'v8': ['icudtl.dat'],
    },
    ext_modules=[
        Extension(
            'v8._v8',
            language='c++',
            sources=[
                'src/module.cc',
            ],
            libraries=[
                'boost_python%s%s' % (
                    sys.version_info.major,
                    sys.version_info.minor,
                ),
                'v8_monolith',
            ],
            extra_compile_args=[
                '-DV8_COMPRESS_POINTERS',
                '-pthread',
                '-std=c++17',
                # Sadly Boost still uses auto_ptr.
                '-Wno-deprecated-declarations',
            ],
        ),
    ],
    zip_safe=False,
)
