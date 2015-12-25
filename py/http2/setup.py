'''Build nghttp2-based HTTP/2 extension with Cython.'''

# Import distutils' Extension class before setuptools patches it.
from distutils.core import Extension as _Extension

import os

from Cython.Build import cythonize
from setuptools import find_packages, setup
from setuptools.extension import Extension


# Create Cython extension objects.


if _Extension is Extension:
    raise RuntimeError('_Extension is %r' % Extension)


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
        'http2/callbacks.c',
        'http2/session.c',
    ],
    libraries=['nghttp2'],
    include_dirs=include_dirs,
    library_dirs=library_dirs,
    extra_compile_args=[
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
    packages = find_packages(exclude=['tests*']),
    ext_modules = ext_modules,
    install_requires = [
        'garage',
    ],
)
