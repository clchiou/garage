from setuptools import setup

setup(
    name='g1.containers',
    packages=[
        'g1.containers',
    ],
    install_requires=[
        'g1.apps',
        'g1.bases',
    ],
    zip_safe=False,
)
