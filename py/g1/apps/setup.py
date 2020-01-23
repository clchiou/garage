from setuptools import setup

from g1.devtools import buildtools

setup(
    name='g1.apps',
    cmdclass={
        'bdist_zipapp': buildtools.make_bdist_zipapp(main_optional=True),
    },
    packages=[
        'g1.apps',
    ],
    install_requires=[
        'g1.bases',
        'startup',
    ],
    extras_require={
        'asyncs': [
            'g1.asyncs.kernels',
        ],
        'yamls': [
            'PyYAML',
        ],
    },
    zip_safe=False,
)
