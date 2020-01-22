from setuptools import setup

setup(
    name='g1.operations',
    entry_points={
        'console_scripts': [
            'ops = g1.operations.apps:run [apps]',
        ],
    },
    packages=[
        'g1.operations',
    ],
    install_requires=[
        'g1.bases',
        'g1.containers',
    ],
    extras_require={
        'apps': [
            'g1.apps',
            'g1.containers[scripts]',
            'g1.scripts[parts]',
        ],
    },
    zip_safe=False,
)
