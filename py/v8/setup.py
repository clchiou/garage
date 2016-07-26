"""Build V8 extension with Cython."""

import os.path
from Cython.Build import cythonize
from distutils.command.build import build
from distutils.core import Command
from distutils.errors import DistutilsOptionError
from distutils.file_util import copy_file
from setuptools import find_packages, setup
from setuptools.extension import Extension


class copy_v8_data(Command):

    description = "copy v8 data blobs"

    user_options = [
        ('v8-out=', None,
         "directory for v8 data blobs"),
    ]

    BLOBS = ('icudtl.dat', 'natives_blob.bin', 'snapshot_blob.bin')

    def initialize_options(self):
        self.v8_out = None

    def finalize_options(self):
        if self.v8_out is None:
            raise DistutilsOptionError('--v8-out is required')
        for blob in self.BLOBS:
            blob_path = os.path.join(self.v8_out, blob)
            if not os.path.exists(blob_path):
                raise DistutilsOptionError('not a file: %s' % blob_path)

    def run(self):
        for blob in self.BLOBS:
            src = os.path.join(self.v8_out, blob)
            dst = os.path.join('v8/data', blob)
            copy_file(src, dst, preserve_mode=False)


build.sub_commands.insert(0, ('copy_v8_data', None))


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
        'copy_v8_data': copy_v8_data,
    },
    packages = find_packages(exclude=['tests*']),
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
