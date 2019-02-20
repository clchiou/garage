from setuptools import setup

setup(
    name='g1.http.spiders',
    packages=[
        'g1.http.spiders',
    ],
    install_requires=[
        'g1.asyncs.bases',
        'g1.bases',
        'g1.http.clients',
    ],
    extras_require={
        'parts': [
            'g1.apps[asyncs]',
            'g1.asyncs.servers',
        ],
    },
    zip_safe=False,
)
