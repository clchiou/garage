from setuptools import setup

setup(
    name='g1.databases',
    packages=[
        'g1.databases',
    ],
    install_requires=[
        'SQLAlchemy',
        'g1.bases',
    ],
    zip_safe=False,
)
