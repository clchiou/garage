__all__ = [
    'HttpServer',
]

import logging
import socket
import ssl
import sys

from . import wsgi

logging.getLogger(__name__).addHandler(logging.NullHandler())

VERSION = '%s/v1' % __name__


class HttpServer:

    def __init__(self, server_socket, application):
        address = server_socket.target.getsockname()
        is_ssl = isinstance(server_socket.target, ssl.SSLSocket)
        self._base_environ = {
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'https' if is_ssl else 'http',
            'wsgi.multithread': True,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
            # Should we wrap sys.stderr in an async adapter?
            'wsgi.errors': sys.stderr,
            'SERVER_SOFTWARE': VERSION,
            'SERVER_NAME': socket.getfqdn(address[0]),
            'SERVER_PORT': address[1],
            'SERVER_PROTOCOL': 'HTTP/1.1',
            'SCRIPT_NAME': '',
        }
        self._application = application

    async def __call__(self, sock, address):
        base_environ = self._base_environ.copy()
        base_environ['REMOTE_ADDR'] = address[0]
        base_environ['REMOTE_PORT'] = address[1]
        session = wsgi.HttpSession(sock, self._application, base_environ)
        return await session()
