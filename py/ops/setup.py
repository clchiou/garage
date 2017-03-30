from setuptools import setup

import buildtools


setup(
    name = 'ops',
    description = 'Operations tool',
    entry_points = {
        'console_scripts': [
            'ops-mob = ops.mob:main',
            'ops-onboard = ops.onboard:main',
        ],
    },
    cmdclass = {
        # For packaging self-contained ops-onboard tool
        'bdist_zipapp': buildtools.make_bdist_zipapp(main='ops.onboard:main'),
    },
    packages = [
        'ops',
        'ops.mob',
        'ops.onboard',
    ],
    install_requires = [
        'garage[components]',
    ],
)
