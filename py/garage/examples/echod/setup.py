from setuptools import setup


setup(
    name = 'echod',
    description = 'Echo service',
    py_modules = ['echod'],
    install_requires = [
        'garage',
        'http2',
    ],
)
