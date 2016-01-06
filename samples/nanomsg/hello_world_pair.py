import asyncio
import sys

import nanomsg as nn
from nanomsg.asyncio import Socket

from utils import Barrier


async def ping(url, barrier):
    with Socket(protocol=nn.NN_PAIR) as sock, sock.connect(url):
        await sock.send(b'ping')
        message = await sock.recv()
        print(bytes(message.as_memoryview()).decode('ascii'))
        await barrier.wait()


async def pong(url, barrier):
    with Socket(protocol=nn.NN_PAIR) as sock, sock.bind(url):
        await sock.send(b'pong')
        message = await sock.recv()
        print(bytes(message.as_memoryview()).decode('ascii'))
        await barrier.wait()


def main():
    url = 'inproc://test'
    barrier = Barrier(2)
    future = asyncio.wait(
        [
            asyncio.ensure_future(ping(url, barrier)),
            asyncio.ensure_future(pong(url, barrier)),
        ],
        return_when=asyncio.FIRST_EXCEPTION)
    loop = asyncio.get_event_loop()
    for fut in loop.run_until_complete(future)[0]:
        fut.result()
    loop.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
