import logging
import sys

import curio

from garage import asyncs
from garage.asyncs.utils import make_server_socket

import http2


async def serve(port, ssl_context=None):
    async with await make_server_socket(('', port)) as server_sock:
        while True:
            sock, addr = await server_sock.accept()
            if ssl_context:
                sock = ssl_context.wrap_socket(sock, server_side=True)
            logging.info('Connection from %s:%d', *addr)
            await asyncs.spawn(handle(sock))


async def handle(sock):
    session = http2.Session(sock)
    async with asyncs.join_on_normal_exit(await asyncs.spawn(session.serve())):
        async for stream in session:
            logging.info('Request: %s %r',
                         stream.request.method.name,
                         stream.request.path.decode('utf8'))
            await stream.submit(http2.Response(body=b'hello world'))


def main():
    if len(sys.argv) < 2:
        print('Usage: %s port [server.crt server.key]' % sys.argv[0])
        sys.exit(1)
    if len(sys.argv) >= 4:
        ssl_context = http2.make_ssl_context(sys.argv[2], sys.argv[3])
    else:
        ssl_context = None
    curio.run(serve(int(sys.argv[1]), ssl_context))


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    main()
