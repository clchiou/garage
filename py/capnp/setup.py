import sys
from setuptools import setup
from setuptools.extension import Extension

import buildtools

BOOST_LIB = 'boost_python{0.major}{0.minor}'.format(sys.version_info)

# You might also need to set PKG_CONFIG_PATH=/path/to/lib/pkgconfig if
# your capnp is installed in a non-default location
CAPNP = buildtools.read_pkg_config(['capnp'])


setup(
    name = 'capnp',
    packages = [
        'capnp',
    ],
    ext_modules = [
        Extension(
            'capnp.native',
            language = 'c++',
            sources = [
                'src/module.cc',
                'src/schema.cc',
                'src/resource-types.cc',
                'src/value-types.cc',
            ],
            include_dirs = CAPNP.include_dirs,
            library_dirs = CAPNP.library_dirs,
            libraries = [BOOST_LIB] + CAPNP.libraries,
            extra_compile_args = ['-std=c++14'] + CAPNP.extra_compile_args,
        ),
    ],
)
