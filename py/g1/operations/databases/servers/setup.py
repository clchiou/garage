from setuptools import setup

setup(
    name='g1.operations.databases.servers',
    packages=[
        'g1.operations.databases.servers',
    ],
    install_requires=[
        'SQLAlchemy',
        'g1.asyncs.bases',
        'g1.bases',
        'g1.databases',
        'g1.operations.databases.bases',
    ],
    extras_require={
        'apps': [
            'g1.apps[asyncs]',
            'g1.asyncs.agents[parts]',
            'g1.asyncs.kernels',
            # Sadly this doesn't seem to work.
            # 'g1.operations.databases.servers[parts]',
        ],
        'parts': [
            'g1.apps',
            'g1.asyncs.agents[parts]',
            'g1.databases[parts]',
            'g1.messaging[parts.servers,reqrep]',
            'g1.operations.databases.bases[capnps]',
        ],
    },
    zip_safe=False,
)
