"""Test fixture setup."""

# TODO: I would like to build an optional test fixture library, but I do
# not know how to express this in ``setup.py``, and so I put this here.
# This is probably not a good practice, and I should rewrite this.

import sys
from setuptools import setup
from setuptools.extension import Extension

from g1.devtools import buildtools

BOOST_LIB = f'boost_python{sys.version_info.major}{sys.version_info.minor}'

# You should set ``PKG_CONFIG_PATH`` environment variable if your
# capnproto library is installed at a non-conventional location.
CAPNP = buildtools.read_package_config(['capnp'])

COMPILE_ARGS = [
    # capnp requires C++14.
    '-std=c++14',
    # boost still uses auto_ptr; this disables warning on that.
    '-Wno-deprecated-declarations',
]

setup(
    name='capnp_test',
    ext_modules=[
        Extension(
            'capnp._capnp_test',
            language='c++',
            sources=[
                'src/module-test.cc',
                # Parts of the module.
                'src/string-test.cc',
                'src/void-test.cc',
            ],
            include_dirs=CAPNP.include_dirs,
            library_dirs=CAPNP.library_dirs,
            libraries=[BOOST_LIB] + CAPNP.libraries,
            extra_compile_args=COMPILE_ARGS + CAPNP.extra_compile_args,
        ),
    ],
    zip_safe=False,
)
