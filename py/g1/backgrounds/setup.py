from setuptools import setup

setup(
    name='g1.backgrounds',
    packages=[
        'g1.backgrounds',
    ],
    install_requires=[],
    extras_require={
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
