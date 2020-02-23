from setuptools import setup

setup(
    name='g1.asyncs.agents',
    packages=[
        'g1.asyncs.agents',
    ],
    install_requires=[
        'g1.asyncs.bases',
    ],
    extras_require={
        'parts': [
            'g1.apps',
            'g1.bases',
            'startup',
        ],
    },
    zip_safe=False,
)
