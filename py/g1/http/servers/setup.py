from setuptools import setup

setup(
    name = 'g1.http.servers',
    packages = [
        'g1.http.servers',
    ],
    install_requires = [
        'g1.asyncs.kernels',
        'g1.asyncs.servers',
        'g1.bases',
        'g1.networks.servers',
    ],
    extras_require = {
        'parts': [
            'g1.apps[asyncs]',
        ],
    },
    zip_safe = False,
)
