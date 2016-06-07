from setuptools import setup


setup(
    name = 'echod',
    description = 'Echo service',
    packages = [
        'echod',
    ],
    install_requires = [
        'garage',
        'http2',
    ],
)
