__all__ = [
    'HttpServer',
    'serve_http',
]

import logging
import socket
import ssl

from g1.networks.servers import TcpServer

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
        self._server_socket = server_socket
        self._application = application

        address = self._server_socket.target.getsockname()
        is_ssl = isinstance(self._server_socket.target, ssl.SSLSocket)
        self._environ = {
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'https' if is_ssl else 'http',
            'wsgi.multithread': True,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
            'SERVER_SOFTWARE': VERSION,
            'SCRIPT_NAME': '',
            'SERVER_NAME': socket.getfqdn(address[0]),
            'SERVER_PORT': address[1],
            'SERVER_PROTOCOL': 'HTTP/2.0',
        }

    async def serve(self):
        server = TcpServer(self._server_socket, self._handle_client)
        return await server.serve()

    async def _handle_client(self, sock, addr):
        environ = self._environ.copy()
        environ['REMOTE_ADDR'] = addr[0]
        environ['REMOTE_PORT'] = addr[1]
        session = wsgi.HttpSession(sock, addr, self._application, environ)
        return await session.serve()


async def serve_http(server_socket, application):
    return await HttpServer(server_socket, application).serve()
