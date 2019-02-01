from setuptools import setup

setup(
    name = 'g1.networks.servers',
    packages = [
        'g1.networks.servers',
    ],
    install_requires = [
        'g1.asyncs.kernels',
    ],
    zip_safe = False,
)
