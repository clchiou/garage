import asyncio
import sys

import nanomsg as nn
from nanomsg.asyncio import Socket

from utils import Barrier


async def ping(url, topic, barrier):
    with Socket(protocol=nn.NN_PUB) as sock, sock.bind(url):
        await sock.send(b'%s|ping' % topic)
        await sock.send(b'NOT-ON-%s|ping' % topic)
        await barrier.wait()


async def pong(url, topic, barrier):
    with Socket(protocol=nn.NN_SUB) as sock:
        sock.setsockopt(nn.NN_SUB, nn.NN_SUB_SUBSCRIBE, topic)
        with sock.connect(url):
            message = await sock.recv()
            print(bytes(message.as_memoryview()).decode('ascii'))
        await barrier.wait()


def main():
    url = 'inproc://test'
    topic = b'TOPIC'
    barrier = Barrier(2)
    future = asyncio.wait(
        [
            asyncio.ensure_future(ping(url, topic, barrier)),
            asyncio.ensure_future(pong(url, topic, barrier)),
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
