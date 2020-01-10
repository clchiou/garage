from setuptools import setup

setup(
    name='g1.scripts',
    packages=[
        'g1.scripts',
    ],
    install_requires=[
        'g1.bases',
    ],
    extras_require={
        'parts': [
            'g1.apps',
        ],
    },
    zip_safe=False,
)
