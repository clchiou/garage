import os.path

from capnptools.buildtools import setup


setup(
    name = 'capnptools examples',
    packages = [
        'examples',
    ],
    capnp_extension_name = 'examples.books',
    capnp_imports = [
        '/examples/books.capnp',
    ],
    capnp_import_paths = [
        os.path.abspath(os.path.curdir),
    ],
)
