from setuptools import setup

setup(
    name='nng',
    packages=[
        'nng',
    ],
    install_requires=[
        'g1.bases',
    ],
    extras_require={
        'asyncs': [
            'g1.asyncs.bases',
            'g1.asyncs.kernels',
        ],
    },
    zip_safe=False,
)
