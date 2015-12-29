import asyncio
import logging
import socket
import sys

import http2

from garage.http import services


if len(sys.argv) < 2:
    print('Usage: %s port' % sys.argv[0])
    sys.exit(1)

logging.basicConfig()

async def hello_world(request):
    print('request:', repr(request))
    return b'hello world'

service = services.Service(services.Version(1, 0, 0))
service.add_endpoint('hello-world', hello_world)

loop = asyncio.get_event_loop()

server = loop.run_until_complete(loop.create_server(
    lambda: http2.Protocol(lambda: service),
    '127.0.0.1', int(sys.argv[1]),
))

server.sockets[0].setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

try:
    loop.run_forever()
except KeyboardInterrupt:
    pass
finally:
    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()
