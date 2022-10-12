from setuptools import setup

setup(
    name='g1.networks.servers',
    packages=[
        'g1.networks.servers',
    ],
    install_requires=[
        'g1.asyncs.bases',
        'g1.bases',
    ],
    extras_require={
        'parts': [
            'g1.apps[asyncs]',
            'g1.asyncs.agents[parts]',
            'g1.bases',
        ],
    },
    zip_safe=False,
)
