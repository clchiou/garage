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
    extras_require={
        'parts': [
            'g1.apps',
        ],
    },
    zip_safe=False,
)
