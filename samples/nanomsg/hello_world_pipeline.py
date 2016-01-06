import asyncio
import sys

import nanomsg as nn
from nanomsg.asyncio import Socket


async def ping(url, ack):
    with Socket(protocol=nn.NN_PUSH) as sock, sock.connect(url):
        await sock.send(b'Hello, World!')
        # Shutdown the endpoint after the other side ack'ed; otherwise
        # the message could be lost.
        await ack.wait()


async def pong(url, ack):
    with Socket(protocol=nn.NN_PULL) as sock, sock.bind(url):
        message = await sock.recv()
        print(bytes(message.as_memoryview()).decode('ascii'))
        ack.set()


def main():
    url = 'inproc://test'
    loop = asyncio.get_event_loop()
    ack = asyncio.Event()
    loop.run_until_complete(asyncio.wait([
        asyncio.ensure_future(ping(url, ack)),
        asyncio.ensure_future(pong(url, ack)),
    ]))
    loop.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
