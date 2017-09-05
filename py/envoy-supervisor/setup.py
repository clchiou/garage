from setuptools import setup


setup(
    name = 'envoy_supervisor',
    packages = [
        'envoy_supervisor',
    ],
    install_requires = [
        'garage[components]',
    ],
)
