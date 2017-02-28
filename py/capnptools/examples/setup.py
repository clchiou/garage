from distutils.command.build import build
import os.path

from Cython.Build import cythonize
from setuptools import setup
from setuptools.extension import Extension

import capnptools.buildtools
import buildtools


PKG_CONFIG = buildtools.read_pkg_config(['capnp'])
PKG_CONFIG.extra_compile_args.insert(0, '-std=c++11')


OUTPUT_DIR = 'build/capnp'


# capnptools.buildtools.compile_schemas() searches capnp schema files
# under PYTHONPATH
PYTHONPATH = os.environ.get('PYTHONPATH')
if PYTHONPATH:
    PYTHONPATH = '%s:%s' % (os.path.abspath(os.path.curdir), PYTHONPATH)
else:
    PYTHONPATH = os.path.abspath(os.path.curdir)
os.environ['PYTHONPATH'] = PYTHONPATH


setup(
    name = 'capnptools examples',
    cmdclass = {
        cmd.__name__: cmd
        for cmd in buildtools.register_subcommands(
            build,
            capnptools.buildtools.make_post_cythonize_fix([
                OUTPUT_DIR + '/examples/books.cpp',
            ]),
        )
    },
    packages = [
        'examples',
    ],
    ext_modules = cythonize(Extension(
        'examples.books',
        language = 'c++',
        sources = capnptools.buildtools.compile_schemas(
            imports = [
                '/examples/books.capnp',
            ],
            output_dir = OUTPUT_DIR,
        ),
        **PKG_CONFIG._asdict(),
    )),
)
