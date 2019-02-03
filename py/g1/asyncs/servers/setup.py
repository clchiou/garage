from setuptools import setup

setup(
    name = 'g1.asyncs.servers',
    packages = [
        'g1.asyncs.servers',
    ],
    install_requires = [
        'g1.asyncs.kernels',
    ],
    zip_safe = False,
)
