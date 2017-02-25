"""A simple HTTP/2 file server."""

import logging
import os.path
import urllib.parse
import sys

import curio
import curio.io

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
            request = stream.request
            if request.method is not http2.Method.GET:
                await stream.submit(
                    http2.Response(status=http2.Status.BAD_REQUEST))
                return

            path = urllib.parse.unquote(request.path.decode('ascii'))
            logging.info('GET %s', path)
            if not path.startswith('/'):
                await stream.submit(
                    http2.Response(status=http2.Status.BAD_REQUEST))
                return
            path = path[1:]

            if not os.path.isfile(path):
                await stream.submit(
                    http2.Response(status=http2.Status.NOT_FOUND))
                return

            try:
                async with curio.io.FileStream(open(path, 'rb')) as contents:
                    body = await contents.readall()
            except OSError:
                logging.exception('Err when read %s', path)
                await stream.submit(
                    http2.Response(status=http2.Status.INTERNAL_SERVER_ERROR))
                return

            await stream.submit(http2.Response(body=body))


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
