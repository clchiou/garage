from setuptools import find_packages, setup

import buildtools


setup(
    name = 'garage',
    description = 'Python modules developed in the garage',
    license = 'MIT',
    cmdclass = {
        'bdist_zipapp': buildtools.make_bdist_zipapp(main_optional=True),
    },
    packages = find_packages(exclude=['tests*']),
    extras_require = {
        'asyncs': ['curio'],
        'components': ['startup'],
        'formatters': ['PyYAML'],
        'http.clients': ['lxml', 'requests'],
        'http.servers': ['http2'],
        'sql': ['SQLAlchemy'],
    },
)
