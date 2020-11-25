from setuptools import setup

setup(
    name='g1.operations.databases.subscribers',
    packages=[
        'g1.operations.databases.subscribers',
    ],
    install_requires=[
        'g1.messaging[pubsub]',
        'g1.operations.databases.bases[capnps]',
    ],
    extras_require={
        'parts': [
            'g1.apps',
            'g1.asyncs.agents[parts]',
            'g1.asyncs.bases',
            'g1.bases',
            'g1.messaging[parts.pubsub]',
        ],
    },
    zip_safe=False,
)
