from setuptools import find_packages, setup


setup(
    name = 'garage',
    description = 'Python modules developed in the garage',
    license = 'MIT',
    packages = find_packages(exclude=['tests*']),
    extras_require = {
        'components': ['startup'],
        'formatters': ['PyYAML'],
        'http.clients': ['lxml', 'requests'],
        'http.servers': ['http2'],
        'sql': ['SQLAlchemy'],
    },
)
