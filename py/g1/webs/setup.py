from setuptools import setup

setup(
    name='g1.webs',
    packages=[
        'g1.webs',
        'g1.webs.handlers',
    ],
    install_requires=[
        'g1.asyncs.bases',
        'g1.asyncs.servers',
        'g1.bases',
    ],
    extras_require={
        'parts': [
            'g1.apps',
            'g1.http.servers[parts]',
        ],
    },
    zip_safe=False,
)
