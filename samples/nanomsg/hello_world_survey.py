import asyncio
import sys

import nanomsg as nn
from nanomsg.asyncio import Socket

from utils import Barrier


async def ping(url, barrier, ack):
    with Socket(protocol=nn.NN_SURVEYOR) as sock, sock.bind(url):
        await sock.send(b'ping')
        await barrier.wait()  # TODO: Figure out why we need this barrier...

        try:
            while True:
                message = await sock.recv()
                print(bytes(message.as_memoryview()).decode('ascii'))
        except nn.NanomsgError as e:
            if e.errno is not nn.Error.ETIMEDOUT:
                raise
        ack.set()


async def pong(url, barrier, ack):
    with Socket(protocol=nn.NN_RESPONDENT) as sock, sock.connect(url):
        message = await sock.recv()
        print(bytes(message.as_memoryview()).decode('ascii'))
        await barrier.wait()  # TODO: Figure out why we need this barrier...

        await sock.send(b'pong')
        await ack.wait()


def main():
    num_respondents = 2
    url = 'inproc://test'
    barrier = Barrier(1 + num_respondents)
    ack = asyncio.Event()
    future = asyncio.wait(
        [
            asyncio.ensure_future(ping(url, barrier, ack)),
        ] + [
            asyncio.ensure_future(pong(url, barrier, ack))
            for _ in range(num_respondents)
        ],
        return_when=asyncio.FIRST_EXCEPTION,
    )

    loop = asyncio.get_event_loop()
    for fut in loop.run_until_complete(future)[0]:
        fut.result()
    loop.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
