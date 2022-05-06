from setuptools import setup

from g1.devtools import buildtools

setup(
    name='g1.scripts',
    cmdclass={
        'bdist_zipapp': buildtools.make_bdist_zipapp(main_optional=True),
    },
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
