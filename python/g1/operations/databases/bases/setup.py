from distutils.command.build import build
from setuptools import setup

from g1.devtools import buildtools
from g1.devtools.buildtools import capnps

setup(
    name='g1.operations.databases.bases',
    cmdclass={
        cmd.__name__: cmd
        for cmd in buildtools.register_subcommands(
            build,
            capnps.make_compile_schemas({
                '/g1/operations/databases.capnp':
                'g1/operations/databases/bases/databases.schema',
            }),
        )
    },
    packages=[
        'g1.operations.databases.bases',
    ],
    package_data={
        'g1.operations.databases.bases': [
            'databases.schema',
        ],
    },
    install_requires=[
        'g1.bases',
        'g1.messaging',
    ],
    extras_require={
        'capnps': [
            'capnp',
            'g1.messaging[wiredata.capnps]',
        ],
    },
    zip_safe=False,
)
