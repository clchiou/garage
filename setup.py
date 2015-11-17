from setuptools import find_packages, setup


setup(
    name = 'garage',
    description = 'Python modules developed in the garage',
    license = 'MIT',
    packages = find_packages(),
    install_requires = [
        # These modules are optional but nice to have.
        #'PyYAML',
        #'lxml',
        #'requests',
        #'startup',
    ],
)
