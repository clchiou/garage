from functools import partial
import logging
import sys

import curio

from garage import asyncs
from garage.asyncs.utils import make_server_socket, serve

import http2


async def handle(sock, addr, ssl_context=None):
    if ssl_context:
        sock = ssl_context.wrap_socket(sock, server_side=True)
    session = http2.Session(sock)
    async with asyncs.cancel_on_exit(
            await asyncs.spawn(session.serve())) as server:
        async for stream in session:
            logging.info('Request: %s %r',
                         stream.request.method.name,
                         stream.request.path.decode('utf8'))
            await stream.submit(http2.Response(body=b'hello world'))
        await server.join()


def main():
    if len(sys.argv) < 2:
        print('Usage: %s port [server.crt server.key]' % sys.argv[0])
        sys.exit(1)
    if len(sys.argv) >= 4:
        ssl_context = http2.make_ssl_context(sys.argv[2], sys.argv[3])
    else:
        ssl_context = None
    curio.run(serve(
        curio.Event(),
        partial(make_server_socket, ('', int(sys.argv[1]))),
        partial(handle, ssl_context=ssl_context),
    ))


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    main()
