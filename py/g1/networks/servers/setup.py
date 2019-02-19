from setuptools import setup

setup(
    name='g1.networks.servers',
    packages=[
        'g1.networks.servers',
    ],
    install_requires=[
        'g1.asyncs.bases',
        'g1.asyncs.servers',
    ],
    extras_require={
        'parts': [
            'g1.apps[asyncs]',
        ],
    },
    zip_safe=False,
)
