from setuptools import setup


setup(
    name = 'envoyd',
    packages = [
        'envoyd',
        'envoyd.roles',
    ],
    install_requires = [
        'garage[components]',
    ],
)
