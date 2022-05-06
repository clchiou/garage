from setuptools import setup

setup(
    name='g1.operations.databases.clients',
    packages=[
        'g1.operations.databases.clients',
    ],
    install_requires=[
        'g1.messaging[reqrep]',
        'g1.operations.databases.bases[capnps]',
    ],
    extras_require={
        'parts': [
            'g1.apps',
            'g1.bases',
            'g1.messaging[parts.clients]',
        ],
    },
    zip_safe=False,
)
