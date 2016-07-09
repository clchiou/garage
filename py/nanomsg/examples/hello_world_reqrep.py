import asyncio
import sys

import nanomsg as nn
from nanomsg.asyncio import Socket


async def ping(url):
    with Socket(protocol=nn.NN_REQ) as sock, sock.connect(url):
        await sock.send(b'ping')
        message = await sock.recv()
        print(bytes(message.as_memoryview()).decode('ascii'))


async def pong(url):
    with Socket(protocol=nn.NN_REP) as sock, sock.bind(url):
        message = await sock.recv()
        print(bytes(message.as_memoryview()).decode('ascii'))
        await sock.send(b'pong')


def main():
    url = 'inproc://test'
    future = asyncio.wait(
        [
            asyncio.ensure_future(ping(url)),
            asyncio.ensure_future(pong(url)),
        ],
        return_when=asyncio.FIRST_EXCEPTION,
    )

    loop = asyncio.get_event_loop()
    done, _ = loop.run_until_complete(future)
    for fut in done:
        fut.result()
    loop.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
