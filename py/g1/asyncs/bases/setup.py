from setuptools import setup

setup(
    name='g1.asyncs.bases',
    packages=[
        'g1.asyncs.bases',
    ],
    install_requires=[
        'g1.asyncs.kernels',
        'g1.bases',
    ],
    zip_safe=False,
)
