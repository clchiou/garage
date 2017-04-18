from setuptools import setup
from setuptools.extension import Extension

setup(
    name = 'test-capnp',
    ext_modules = [
        Extension(
            'extension',
            language = 'c++',
            sources = [
                'extension.cc',
            ],
            libraries = ['boost_python3'],
            extra_compile_args = ['-std=c++11'],
        ),
    ],
)
