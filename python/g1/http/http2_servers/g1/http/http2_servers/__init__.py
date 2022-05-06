__all__ = [
    'HttpServer',
]

import logging
import socket
import ssl

from . import nghttp2 as ng
from . import wsgi

logging.getLogger(__name__).addHandler(logging.NullHandler())

VERSION = '%s/nghttp2=%s' % (
    __name__,
    # pylint: disable=no-member
    ng.F.nghttp2_version(0).contents.version_str.decode('utf-8'),
)


class HttpServer:

    def __init__(self, server_socket, application):
        address = server_socket.getsockname()
        is_ssl = isinstance(server_socket.target, ssl.SSLSocket)
        self._environ = {
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'https' if is_ssl else 'http',
            'wsgi.multithread': True,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
            'SERVER_SOFTWARE': VERSION,
            'SERVER_NAME': socket.getfqdn(address[0]),
            'SERVER_PORT': address[1],
            'SERVER_PROTOCOL': 'HTTP/2.0',
        }
        self._application = application

    async def __call__(self, client_socket, address):
        environ = self._environ.copy()
        environ['REMOTE_ADDR'] = address[0]
        environ['REMOTE_PORT'] = address[1]
        session = wsgi.HttpSession(
            client_socket, address, self._application, environ
        )
        return await session.serve()
