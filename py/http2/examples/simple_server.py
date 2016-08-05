"""A simple HTTP/2 file server."""

import asyncio
import logging
import sys
from concurrent.futures.thread import ThreadPoolExecutor

import os.path
import urllib.parse
from http import HTTPStatus

import http2.utils
from http2 import HttpError, Protocol


LOG = logging.getLogger(__name__)


class Handler:

    def __init__(self, root_path=os.path.curdir, *, loop=None):
        self.root_path = root_path
        self.executor = ThreadPoolExecutor(max_workers=8)
        self.loop = loop or asyncio.get_event_loop()

    async def __call__(self, request, response):
        try:
            path = request.headers.get(b':path')
            if path is None:
                raise HttpError(HTTPStatus.BAD_REQUEST)
            path = urllib.parse.unquote(path.decode('ascii'))
            assert path.startswith('/')

            local_path = os.path.join(self.root_path, path[1:])
            if not os.path.isfile(local_path):
                raise HttpError(HTTPStatus.NOT_FOUND)

            LOG.info('GET %s', path)
            with open(local_path, 'rb') as data:
                contents = await self.loop.run_in_executor(
                    self.executor, data.read)

            response.headers[b':status'] = b'200'
            await response.write(contents)
            response.close()

        except HttpError:
            raise
        except Exception:
            LOG.exception('error when processing request')
            raise HttpError(HTTPStatus.INTERNAL_SERVER_ERROR)


def main(argv):
    if len(argv) < 2 or argv[1] == '-h':
        print('Usage: %s [-h] port [server.crt server.key]' % argv[0])
        return 0

    logging.basicConfig(level=logging.DEBUG)

    if len(argv) >= 4:
        ssl_context = http2.utils.make_ssl_context(argv[2], argv[3])
    else:
        ssl_context = None

    loop = asyncio.get_event_loop()

    handler = Handler()
    server = loop.run_until_complete(loop.create_server(
        lambda: Protocol(lambda: handler),
        host='0.0.0.0', port=int(argv[1]), ssl=ssl_context,
    ))

    print('Serving on port %s' % argv[1])
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        loop.run_until_complete(server.wait_closed())
        loop.close()

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))