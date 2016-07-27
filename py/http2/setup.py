"""Build nghttp2-based HTTP/2 extension with Cython."""

import os
from Cython.Build import cythonize
from setuptools import setup
from setuptools.extension import Extension


#
# NOTE: You will need to add these to the build_ext command if nghttp2
# is not installed under default search locations like /usr/local.
#
#   --include-dirs "/path/to/nghttp2/include"
#   --library-dirs "/path/to/nghttp2/lib"
#
setup(
    name = 'http2',
    license = 'MIT',
    packages = ['http2'],
    ext_modules = cythonize(Extension(
        'http2.http2',
        sources = [
            'http2/http2.pyx',
            'http2/base.c',
            'http2/builder.c',
            'http2/callbacks.c',
            'http2/session.c',
            'http2/stream.c',
        ],
        libraries = ['nghttp2'],
        include_dirs = ['.'],
        undef_macros = ['NDEBUG'] if os.getenv('DEBUG') else None,
        extra_compile_args = [
            '-std=c99',
            '-Werror',
            '-Wall',
            '-Wextra',
            '-Wno-unused-parameter',
        ],
    )),
)
