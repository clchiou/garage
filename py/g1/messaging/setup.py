from setuptools import setup

setup(
    name='g1.messaging',
    packages=[
        'g1.messaging',
        'g1.messaging.wiredata',
    ],
    install_requires=[
        'g1.bases',
    ],
    zip_safe=False,
)
