from setuptools import setup

setup(
    name='g1.http.http1_servers',
    packages=[
        'g1.http.http1_servers',
    ],
    install_requires=[
        'g1.asyncs.bases',
        'g1.bases',
    ],
    extras_require={
        'parts': [
            'g1.apps',
            'g1.networks.servers[parts]',
        ],
    },
    zip_safe=False,
)
