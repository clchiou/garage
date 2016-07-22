'''Build V8 extension with Cython.'''

# Import distutils' Extension class before setuptools patches it.
from distutils.core import Extension as _Extension

import os
import os.path

from Cython.Build import cythonize
from setuptools import find_packages, setup
from setuptools.extension import Extension


V8 = os.getenv('V8')
V8_OUT = os.getenv('V8_OUT')
if None in (V8, V8_OUT):
    raise RuntimeError('V8 and V8_OUT are required')
V8 = os.path.realpath(V8)
V8_OUT = os.path.realpath(V8_OUT)


# distutils and setuptools are VERY brittle - I can't extend the `build`
# and `develop` command to link V8 natives and snapshot blob without
# breaking anything.  To workaround this difficulty, I will just get
# those file paths from environment variable and do the linking myself.


for filename in ('icudtl.dat', 'natives_blob.bin', 'snapshot_blob.bin'):
    src = os.path.join(V8_OUT, filename)
    dst = os.path.join('v8/data', filename)
    if not os.path.exists(src):
        raise RuntimeError('%s does not exist' % src)
    if os.path.lexists(dst):
        if os.path.samefile(src, dst):
            continue
        else:
            raise RuntimeError('%s exists' % dst)
    print('linking %s -> %s' % (dst, src))
    os.symlink(src, dst)


# Create Cython extension objects.


if _Extension is Extension:
    raise RuntimeError('_Extension is %r' % Extension)


_ext_modules = cythonize(_Extension(
    'v8.v8',
    language='c++',
    sources=['v8/v8.pyx'],
    include_dirs=[V8, os.path.join(V8, 'include')],
    library_dirs=[
        os.path.join(V8_OUT, 'lib.target'),
        os.path.join(V8_OUT, 'obj.target/src'),
    ],
    libraries=[
        'icui18n',
        'icuuc',
        'v8',
        'v8_libbase',
        'v8_libplatform',
    ],
    extra_compile_args=[
        '-std=c++11',
        '-fno-exceptions',
        '-fno-rtti',
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
    name = 'v8',
    license = 'MIT',
    packages = find_packages(exclude=['tests*']),
    ext_modules = ext_modules,
    package_data = {
        'v8': [
            'data/icudtl.dat',
            'data/natives_blob.bin',
            'data/snapshot_blob.bin',
        ],
    },
)
