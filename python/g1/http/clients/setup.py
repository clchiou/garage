from setuptools import setup

setup(
    name='g1.http.clients',
    packages=[
        'g1.http.clients',
        'g1.http.clients.parts',
    ],
    install_requires=[
        'g1.asyncs.bases',
        'g1.bases',
        'g1.threads',
        'lxml',
        'requests',
        # Use urllib3 pulled in by requests.
        # 'urllib3',
    ],
    extras_require={
        'parts': [
            'g1.apps[asyncs]',
        ],
    },
    zip_safe=False,
)
