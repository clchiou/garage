from setuptools import setup

from g1.devtools import buildtools

setup(
    name='g1.containers',
    entry_points={
        'console_scripts': [
            'ctr = g1.containers.apps:run [apps]',
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
        'g1.bases',
    ],
    extras_require={
        'apps': [
            'g1.apps',
            'g1.scripts[parts]',
            'g1.texts',
        ],
        'scripts': [
            'g1.scripts',
        ],
    },
    zip_safe=False,
)
