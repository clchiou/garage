from setuptools import setup

from g1.devtools import buildtools

setup(
    name='g1.containers',
    entry_points={
        'console_scripts': [
            'ctr = g1.containers.apps:run',
        ],
    },
    cmdclass={
        'bdist_zipapp':
        buildtools.make_bdist_zipapp(main='g1.containers.apps:run'),
    },
    packages=[
        'g1.containers',
    ],
    install_requires=[
        'g1.apps',
        'g1.bases',
        'g1.scripts[parts]',
    ],
    zip_safe=False,
)
