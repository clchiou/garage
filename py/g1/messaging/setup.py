from setuptools import setup

setup(
    name='g1.messaging',
    packages=[
        'g1.messaging',
        'g1.messaging.parts',
        'g1.messaging.reqrep',
        'g1.messaging.wiredata',
    ],
    install_requires=[
        'g1.bases',
    ],
    extras_require={
        'parts.clients': [
            'g1.apps[asyncs]',
        ],
        'parts.servers': [
            'g1.apps[asyncs]',
            'g1.asyncs.agents[parts]',
        ],
        'reqrep': [
            'nng[asyncs]',
        ],
        'wiredata.capnps': [
            'capnp',
        ],
    },
    zip_safe=False,
)
