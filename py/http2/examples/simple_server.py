"""A simple HTTP/2 file server."""

from functools import partial
import logging
import os.path
import urllib.parse
import sys

import curio
import curio.io

from garage import asyncs
from garage.asyncs.utils import make_server_socket, serve

import http2


async def handle(sock, addr):
    session = http2.Session(sock)
    async with await asyncs.cancelling.spawn(session.serve()) as server:
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
                # open() is blocking; an alternative is curio.aopen(),
                # but it secretly uses thread behind the scene, which
                # might be undesirable
                async with curio.io.FileStream(open(path, 'rb')) as contents, \
                           stream.make_buffer() as buffer:
                    await stream.submit(http2.Response(body=buffer))
                    while True:
                        data = await contents.read(65536)
                        if not data:
                            break
                        await buffer.write(data)
            except OSError:
                logging.exception('err when read %s', path)

        await server.join()


def main():
    if len(sys.argv) < 2:
        print('Usage: %s port [server.crt server.key]' % sys.argv[0])
        sys.exit(1)
    if len(sys.argv) >= 4:
        make_ssl_context = partial(
            http2.make_ssl_context, sys.argv[2], sys.argv[3])
    else:
        make_ssl_context = None
    curio.run(serve(
        curio.Event(),
        partial(make_server_socket, ('', int(sys.argv[1]))),
        handle,
        make_ssl_context=make_ssl_context,
    ))


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    main()
