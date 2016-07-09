'''Build nghttp2-based HTTP/2 extension with Cython.'''

# Import distutils' Extension class before setuptools patches it.
from distutils.core import Extension as _Extension

import os

from Cython.Build import cythonize
from setuptools import setup
from setuptools.extension import Extension


# Create Cython extension objects.


if _Extension is Extension:
    raise RuntimeError('_Extension is %r' % Extension)


if os.getenv('DEBUG'):
    undef_macros = ['NDEBUG']
else:
    undef_macros = []


include_dirs = ['.']
if os.getenv('NGHTTP2_INCLUDEDIR'):
    include_dirs.append(os.getenv('NGHTTP2_INCLUDEDIR'))

library_dirs = []
if os.getenv('NGHTTP2_LIBRARYDIR'):
    library_dirs.append(os.getenv('NGHTTP2_LIBRARYDIR'))

_ext_modules = cythonize(_Extension(
    'http2.http2',
    sources=[
        'http2/http2.pyx',
        'http2/base.c',
        'http2/builder.c',
        'http2/callbacks.c',
        'http2/session.c',
        'http2/stream.c',
    ],
    libraries=['nghttp2'],
    include_dirs=include_dirs,
    library_dirs=library_dirs,
    undef_macros=undef_macros,
    extra_compile_args=[
        '-std=c99',
        '-Werror',
        '-Wall',
        '-Wextra',
        '-Wno-unused-parameter',
    ],
))


ext_modules = []
for _ext_module in _ext_modules:
    if not isinstance(_ext_module, _Extension):
        raise RuntimeError('%r is not of type %r' % (_ext_module, _Extension))
    # Translate distutils' Extension to setuptools' Extension.
    ext_module = Extension(**_ext_module.__dict__)
    ext_modules.append(ext_module)


# Build package.


setup(
    name = 'http2',
    license = 'MIT',
    packages = ['http2'],
    ext_modules = ext_modules,
)
