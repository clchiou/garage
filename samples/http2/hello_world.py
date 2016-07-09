import asyncio
import logging
import ssl
import sys

import http2

from garage.http.routers import ApiRouter


if len(sys.argv) < 2:
    print('Usage: %s port [server.crt server.key]' % sys.argv[0])
    sys.exit(1)

logging.basicConfig(level=logging.DEBUG)

async def hello_world(request, response):
    for name, value in request.headers.items():
        print('HEADER %s=%s' % (name.decode('ascii'), value.decode('ascii')))
    response.headers[b':status'] = b'200'
    await response.write(b'hello world')
    response.close()

router = ApiRouter(name='hello-world', version=1)
router.add_handler('hello-world', hello_world)

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
