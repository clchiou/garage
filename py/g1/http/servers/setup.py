from setuptools import setup

setup(
    name = 'g1.http.servers',
    packages = [
        'g1.http.servers',
    ],
    install_requires = [
        'g1.bases',
        'g1.asyncs.kernels',
        'g1.asyncs.servers',
        'g1.networks.servers',
    ],
    zip_safe = False,
)