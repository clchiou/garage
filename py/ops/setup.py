from setuptools import setup

import buildtools


setup(
    name = 'ops',
    description = 'Operation tools',
    cmdclass = {
        'bdist_zipapp': buildtools.make_bdist_zipapp(main='ops:main'),
    },
    packages = [
        'ops',
        'ops.pods',
    ],
)
