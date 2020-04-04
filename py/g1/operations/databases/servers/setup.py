from setuptools import setup

setup(
    name='g1.operations.databases.servers',
    packages=[
        'g1.operations.databases.servers',
    ],
    install_requires=[
        'SQLAlchemy',
        'g1.asyncs.bases',
        'g1.bases',
        'g1.databases',
        'g1.operations.databases.bases',
    ],
    zip_safe=False,
)
