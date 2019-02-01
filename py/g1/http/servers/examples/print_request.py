"""Simple web app that prints out requests."""

import json
import logging
import sys

from g1.asyncs import kernels
from g1.http.servers import serve_http
from g1.networks.servers import make_server_socket


async def application(environ, start_response):
    response = environ.copy()
    response.pop('wsgi.input')
    response.pop('wsgi.errors')
    response = {
        'environ': response,
        'request_body_size': len(await environ['wsgi.input'].read()),
    }
    response = json.dumps(response, indent=4).encode('utf-8')
    start_response(
        '200 OK',
        [
            ('Content-Type', 'application/json'),
            ('Content-Length', str(len(response))),
        ],
    )
    return [response]


def main(argv):
    if len(argv) < 2:
        print('usage: %s port' % argv[0], file=sys.stderr)
        return 1
    logging.basicConfig(level=logging.DEBUG)
    server_socket = make_server_socket(
        ('127.0.0.1', int(argv[1])),
        reuse_address=True,
        reuse_port=True,
    )
    kernels.run(serve_http(server_socket, application))
    return 0


if __name__ == '__main__':
    sys.exit(kernels.call_with_kernel(main, sys.argv))
