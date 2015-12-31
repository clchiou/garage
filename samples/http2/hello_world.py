import asyncio
import logging
import socket
import ssl
import sys

import http2

from garage.http.services import Service


if len(sys.argv) < 2:
    print('Usage: %s port [server.crt server.key]' % sys.argv[0])
    sys.exit(1)

logging.basicConfig()

async def hello_world(request):
    print('request:', repr(request))
    return b'hello world'

service = Service(name='hello-world', version=1)
service.add_endpoint('hello-world', hello_world)

loop = asyncio.get_event_loop()

if len(sys.argv) >= 4:
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    ssl_context.load_cert_chain(sys.argv[2], sys.argv[3])
    if ssl.HAS_ALPN:
        ssl_context.set_alpn_protocols(['h2'])
    else:
        assert ssl.HAS_NPN
        ssl_context.set_npn_protocols(['h2'])
else:
    ssl_context = None

server = loop.run_until_complete(loop.create_server(
    lambda: http2.Protocol(lambda: service),
    host='127.0.0.1', port=int(sys.argv[1]), ssl=ssl_context,
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
