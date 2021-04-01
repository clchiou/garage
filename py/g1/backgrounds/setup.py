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
        'monitors': [
            'g1.apps',
            'g1.asyncs.bases',
            'g1.asyncs.kernels',
            'g1.bases',
            # Sadly setup.py cannot depend itself.
            # 'g1.backgrounds[tasks]',
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
