"""Build capnptools."""

import os.path
from distutils import log
from distutils.command.build import build
from distutils.core import Command
from distutils.errors import DistutilsOptionError
from subprocess import check_call

from Cython.Build import cythonize
from setuptools import setup
from setuptools.extension import Extension

import buildtools


# You might also need to set PKG_CONFIG_PATH=/path/to/lib/pkgconfig if
# your capnp is installed in a non-default location.
PKG_CONFIG = buildtools.read_pkg_config(['capnp'])


# capnp generates files with .c++ suffix.
buildtools.add_cplusplus_suffix('.c++')


class compile_schema(Command):

    description = 'compile /capnp/schema.capnp to c++'

    user_options = [
        ('schema=', None, 'path to schema.capnp file'),
    ]

    def initialize_options(self):
        self.schema = None

    def finalize_options(self):
        if self.schema is None:
            raise DistutilsOptionError('--schema is required')
        if not os.path.exists(self.schema):
            raise DistutilsOptionError('not a file: %s' % self.schema)

    def run(self):
        cmd = [
            'capnp',
            'compile',
            '--src-prefix=%s' % os.path.dirname(self.schema),
            '-oc++:capnptools',
            self.schema,
        ]
        log.info('execute: %s', ' '.join(cmd))
        check_call(cmd)


buildtools.register_subcommands(build, compile_schema)


setup(
    name = 'capnptools',
    license = 'MIT',
    cmdclass = {
        compile_schema.__name__: compile_schema,
    },
    entry_points = {
        'console_scripts': [
            'capnpc-pyx = capnptools.compiler:main',
        ],
    },
    packages = [
        'capnptools',
    ],
    ext_modules = cythonize(Extension(
        'capnptools.schema',
        language = 'c++',
        sources = [
            'capnptools/schema.capnp.c++',
            'capnptools/schema.pyx',
        ],
        include_dirs = PKG_CONFIG.include_dirs,
        library_dirs = PKG_CONFIG.library_dirs,
        libraries = PKG_CONFIG.libraries,
        extra_compile_args = ['-std=c++11'] + PKG_CONFIG.extra_compile_args,
    )),
    package_data = {
        'capnptools': [
            'templates/*',
        ],
    },
    install_requires = [
        'mako',
    ],
)
