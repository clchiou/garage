import asyncio
import logging
import ssl
import sys

import http2
import http2.utils

from garage.http.handlers import ApiHandler
from garage.http.routers import ApiRouter


if len(sys.argv) < 2:
    print('Usage: %s port [server.crt server.key]' % sys.argv[0])
    sys.exit(1)


logging.basicConfig(level=logging.DEBUG)


async def print_headers(headers):
    for name, value in headers.items():
        print('HEADER %s=%s' % (name.decode('ascii'), value.decode('ascii')))


async def hello_world(_):
    return b'hello world'


handler = ApiHandler(hello_world)
handler.add_policy(print_headers)

router = ApiRouter(name='hello-world', version=1)
router.add_handler('hello-world', handler)

loop = asyncio.get_event_loop()

if len(sys.argv) >= 4:
    ssl_context = http2.utils.make_ssl_context(sys.argv[2], sys.argv[3])
else:
    ssl_context = None

server = loop.run_until_complete(loop.create_server(
    lambda: http2.Protocol(lambda: router),
    host='0.0.0.0', port=int(sys.argv[1]), ssl=ssl_context,
))

try:
    loop.run_forever()
except KeyboardInterrupt:
    pass
finally:
    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()
