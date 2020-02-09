from setuptools import setup

setup(
    name='g1.messaging',
    packages=[
        'g1.messaging',
        'g1.messaging.reqrep',
        'g1.messaging.wiredata',
    ],
    install_requires=[
        'g1.bases',
    ],
    extras_require={
        'parts': [
            'g1.apps',
            'g1.asyncs.servers[parts]',
        ],
        'reqrep': [
            'g1.asyncs.bases',
            'nng[asyncs]',
        ],
        'wiredata.capnps': [
            'capnp',
        ],
    },
    zip_safe=False,
)
