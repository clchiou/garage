from setuptools import setup

from g1.devtools import buildtools

setup(
    name='g1.files',
    cmdclass={
        'bdist_zipapp': buildtools.make_bdist_zipapp(main_optional=True),
    },
    packages=[
        'g1.files',
    ],
    install_requires=[
        'g1.bases',
    ],
    zip_safe=False,
)
