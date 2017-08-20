from setuptools import setup
from setuptools.extension import Extension

import buildtools


LIBJPEG = buildtools.read_pkg_config(['libjpeg'])


setup(
    name = 'imagetools',
    packages = [
        'imagetools',
    ],
    ext_modules = [
        Extension(
            'imagetools._imagetools',
            language = 'c',
            sources = [
                'src/module.c',
            ],
            include_dirs = LIBJPEG.include_dirs,
            library_dirs = LIBJPEG.library_dirs,
            libraries = LIBJPEG.libraries,
            extra_compile_args = [
                '-std=c11',
                '-Wall',
                '-Wextra',
            ] + LIBJPEG.extra_compile_args,
        ),
    ],
)
