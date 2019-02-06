from setuptools import setup

setup(
    name = 'g1.apps',
    packages = [
        'g1.apps',
    ],
    install_requires = [
        'g1.bases',
        'startup',
    ],
    extras_require = {
        'asyncs': [
            'g1.asyncs.kernels',
        ],
    },
    zip_safe = False,
)
