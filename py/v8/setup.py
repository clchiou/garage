"""Build V8 extension with Cython."""

from Cython.Build import cythonize
from distutils.command.build import build
from setuptools import setup
from setuptools.extension import Extension

import buildtools


#
# NOTE: You will need to add these to the build_ext command:
#
#   --include-dirs "${V8}/include"
#   --library-dirs "${V8_OUT}/lib.target:${V8_OUT}/obj.target/src"
#
setup(
    name = 'v8',
    license = 'MIT',
    cmdclass = {
        cmd.__name__: cmd
        for cmd in buildtools.register_subcommands(
            build,
            buildtools.make_copy_files(
                filenames=[
                    'icudtl.dat',
                    'natives_blob.bin',
                    'snapshot_blob.bin',
                ],
                dst_dir='v8/data',
            ),
        )
    },
    packages = ['v8'],
    ext_modules = cythonize(Extension(
        'v8.v8',
        language = 'c++',
        sources = ['v8/v8.pyx'],
        libraries = [
            'icui18n',
            'icuuc',
            'v8',
            'v8_libbase',
            'v8_libplatform',
        ],
        extra_compile_args = [
            '-std=c++11',
            '-fno-exceptions',
            '-fno-rtti',
        ],
    )),
    package_data = {
        'v8': [
            'data/icudtl.dat',
            'data/natives_blob.bin',
            'data/snapshot_blob.bin',
        ],
    },
)
