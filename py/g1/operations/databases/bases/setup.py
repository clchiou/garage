from setuptools import setup

setup(
    name='g1.operations.databases.bases',
    packages=[
        'g1.operations.databases.bases',
    ],
    install_requires=[
        'g1.bases',
        'g1.messaging',
    ],
    zip_safe=False,
)
