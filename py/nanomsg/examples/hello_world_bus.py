import asyncio
import sys

import nanomsg as nn
from nanomsg.asyncio import Socket

from utils import Barrier


async def ping(url, barrier):
    with Socket(protocol=nn.NN_BUS) as sock, sock.bind(url):
        await sock.send(b'ping')
        await barrier.wait()


async def pong(url, barrier):
    with Socket(protocol=nn.NN_BUS) as sock, sock.connect(url):
        message = await sock.recv()
        print(bytes(message.as_memoryview()).decode('ascii'))
        await barrier.wait()


def main():
    num_receivers = 3
    url = 'inproc://test'
    barrier = Barrier(1 + num_receivers)
    future = asyncio.wait(
        [
            asyncio.ensure_future(ping(url, barrier)),
        ] + [
            asyncio.ensure_future(pong(url, barrier))
            for _ in range(num_receivers)
        ],
        return_when=asyncio.FIRST_EXCEPTION)
    loop = asyncio.get_event_loop()
    for fut in loop.run_until_complete(future)[0]:
        fut.result()
    loop.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
