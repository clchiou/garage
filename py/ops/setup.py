from setuptools import setup

import buildtools


setup(
    name = 'ops',
    description = 'Operations tool',
    cmdclass = {
        'bdist_zipapp': buildtools.make_bdist_zipapp(main='ops:main'),
    },
    packages = [
        'ops',
        'ops.pods',
    ],
    install_requires = [
        'garage',
    ],
)
