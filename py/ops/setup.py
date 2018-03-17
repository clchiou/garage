from setuptools import setup

import buildtools


setup(
    name = 'ops',
    description = 'Operations tool',
    entry_points = {
        'console_scripts': [
            'ops-mob = ops.mob:run_main',
            'ops-onboard = ops.onboard:run_main',
        ],
    },
    cmdclass = {
        # For packaging self-contained ops-onboard tool
        'bdist_zipapp':
            buildtools.make_bdist_zipapp(main='ops.onboard:run_main'),
    },
    packages = [
        'ops',
        'ops.mob',
        'ops.onboard',
    ],
    package_data = {
        'ops.mob': [
            'templates/*',
        ],
    },
    install_requires = [
        'garage[parts]',
    ],
)
