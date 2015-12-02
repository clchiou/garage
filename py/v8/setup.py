from setuptools import find_packages, setup


setup(
    name = 'v8',
    license = 'MIT',
    packages = find_packages(exclude=['tests*']),
    install_requires = [
        'garage',
    ]
)
