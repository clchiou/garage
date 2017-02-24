"""HTTP/2 server using nghttp2 and ctypes."""

from setuptools import setup


setup(
    name = 'http2',
    description = __doc__,
    license = 'MIT',
    packages = ['http2'],
    install_requires = [
        'curio',
        'garage[asyncs]',
    ],
)
