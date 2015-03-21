from setuptools import find_packages, setup


setup(
    name = 'garage',
    description = 'My personal python modules',
    license = 'MIT',
    packages = find_packages(include=['garage', 'garage.*']),
)
