from setuptools import setup

setup(
    name='g1.backgrounds',
    packages=[
        'g1.backgrounds',
    ],
    install_requires=[],
    extras_require={
        'consoles': [
            'g1.apps[asyncs]',
            'g1.asyncs.agents[parts]',
            'g1.asyncs.bases',
            'g1.bases',
            'g1.networks.servers',
            'g1.threads',
        ],
        'executors': [
            'g1.threads[parts]',
        ],
        'tasks': [
            'g1.asyncs.agents[parts]',
            'g1.asyncs.bases',
            'g1.bases',
            'startup',
        ],
    },
    zip_safe=False,
)
