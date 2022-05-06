from setuptools import setup

from g1.devtools import buildtools

setup(
    name='g1.texts',
    cmdclass={
        'bdist_zipapp': buildtools.make_bdist_zipapp(main_optional=True),
    },
    packages=[
        'g1.texts',
        'g1.texts.columns',
    ],
    install_requires=[
        'g1.bases',
    ],
    extras_require={
        'yamls': [
            'PyYAML',
        ],
    },
    zip_safe=False,
)
