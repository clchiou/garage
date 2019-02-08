from setuptools import setup

setup(
    name = 'g1.threads',
    packages = [
        'g1.threads',
    ],
    install_requires = [
        'g1.bases',
    ],
    extras_require = {
        'parts': [
            'g1.apps',
        ],
    },
    zip_safe = False,
)
