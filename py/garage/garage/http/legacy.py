"""\
Legacy HTTP server.

This module uses standard library's HTTP server implementation, and thus
is not suitable for heavy loads, but on the bright side, since it has no
external dependency, you may find it useful in extreme circumstances.
"""

__all__ = [
    'make_ssl_context',
    'api_server',
]

from concurrent import futures
from http import HTTPStatus
import http.server
import logging
import json
import ssl

from garage.assertions import ASSERT
from garage.threads import actors
from garage.threads import queues


LOG = logging.getLogger(__name__)


def make_ssl_context(certfile, keyfile, *, client_authentication=False):
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(certfile, keyfile)
    if client_authentication:
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.load_verify_locations(cafile=certfile)
    if ssl.HAS_ALPN:
        ssl_context.set_alpn_protocols(['http/1.1'])
    if ssl.HAS_NPN:
        ssl_context.set_npn_protocols(['http/1.1'])
    return ssl_context


@actors.OneShotActor.from_func
def api_server(*,
        name=__name__, version='<?>',
        address,
        make_ssl_context=None,
        request_queue, request_timeout=None):
    """A naive JSON-RPC server."""

    class Server(http.server.HTTPServer):

        def service_actions(self):
            if request_queue.is_closed():
                # HACK: This is a non-blocking version of shutdown().
                # We need this hack because calling self.shutdown() in
                # service_actions() will result in deadlock.
                ASSERT.true(hasattr(self, '_BaseServer__shutdown_request'))
                self._BaseServer__shutdown_request = True

    class Handler(http.server.BaseHTTPRequestHandler):

        protocol_version = 'HTTP/1.1'

        # Control the 'Server' header of responses.
        server_version = name
        sys_version = version

        def do_POST(self):
            LOG.info('serve request from %s:%s', *self.client_address)

            try:
                length = int(self.headers.get('content-length'))
                if length <= 0:
                    request = None
                else:
                    request = self.rfile.read(length)
                    if length != len(request):
                        raise IOError('expect %d bytes but get %d' %
                                      (length, len(request)))
                    request = json.loads(request.decode('utf8'))
            except Exception:
                LOG.exception('reject request')
                self.__send_error(HTTPStatus.BAD_REQUEST)
                return

            response_future = futures.Future()
            try:
                request_queue.put((request, response_future))
            except queues.Closed:
                LOG.warning('drop request since request_queue is closed: %r',
                            request)
                self.__send_error(HTTPStatus.SERVICE_UNAVAILABLE)
                return

            try:
                response = response_future.result(timeout=request_timeout)
                response = json.dumps(response).encode('utf8')
            except futures.TimeoutError:
                LOG.error('timeout on processing request: %r', request)
                self.__send_error(HTTPStatus.SERVICE_UNAVAILABLE)
                return
            except Exception:
                LOG.exception('fail to process request: %r', request)
                self.__send_error(HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(response))
            self.end_headers()
            self.wfile.write(response)

        def __send_error(self, status):
            self.send_response(status)
            self.send_header('Content-Length', 0)
            self.end_headers()

        def log_request(self, code='-', size='-'):
            pass  # Silence BaseHTTPRequestHandler.

    with Server(address, Handler) as server:
        LOG.info('serve HTTP on %s:%s', *server.socket.getsockname())
        if make_ssl_context:
            server.socket = make_ssl_context().wrap_socket(
                server.socket, server_side=True)
        server.serve_forever()

    LOG.info('exit')
