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
    name='capnp',
    packages=[
        'capnp',
    ],
    ext_modules=[
        Extension(
            'capnp._capnp',
            language='c++',
            sources=[
                'src/module.cc',
                # Parts of the module.
                'src/any.cc',
                'src/array.cc',
                'src/dynamic.cc',
                'src/schema-loader.cc',
                'src/schema.cc',
                'src/string.cc',
                'src/void.cc',
            ],
            include_dirs=CAPNP.include_dirs,
            library_dirs=CAPNP.library_dirs,
            libraries=[BOOST_LIB] + CAPNP.libraries,
            extra_compile_args=COMPILE_ARGS + CAPNP.extra_compile_args,
        ),
    ],
    install_requires=[
        'g1.bases',
    ],
    zip_safe=False,
)
