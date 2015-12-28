import asyncio
import socket
import sys

import http2


if len(sys.argv) < 2:
    print('Usage: %s port' % sys.argv[0])
    sys.exit(1)


async def handler(request, response):
    method = request.headers[b':method'].decode('ascii')
    path = request.headers[b':path'].decode('ascii')
    print('%s %s' % (method.upper(), path))
    response.headers[b':status'] = b'200'
    response.write(b'Hello, World!\n')
    response.close()


loop = asyncio.get_event_loop()

server = loop.run_until_complete(loop.create_server(
    lambda: http2.Protocol(lambda: handler),
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
