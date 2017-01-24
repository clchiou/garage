from setuptools import setup


setup(
    name = 'nanomsg',
    packages = ['nanomsg'],
    extras_require = {
        'curio': ['curio'],
    },
)
