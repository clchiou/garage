import asyncio
import sys

import nanomsg as nn
from nanomsg.asyncio import Socket


async def ping(url, barrier):
    with Socket(protocol=nn.NN_PUSH) as sock, sock.connect(url):
        await sock.send(b'Hello, World!')
        # Shutdown the endpoint after the other side ack'ed; otherwise
        # the message could be lost.
        await barrier.wait()


async def pong(url, barrier):
    with Socket(protocol=nn.NN_PULL) as sock, sock.bind(url):
        message = await sock.recv()
        print(bytes(message.as_memoryview()).decode('ascii'))
        await barrier.wait()


async def close_loop(barrier):
    await barrier.wait()
    asyncio.get_event_loop().stop()


class Barrier:

    def __init__(self, parties, *, loop=None):
        self.parties = parties
        self._cond = asyncio.Condition(loop=loop)

    async def wait(self):
        await self._cond.acquire()
        try:
            assert self.parties > 0
            self.parties -= 1
            if self.parties > 0:
                await self._cond.wait()
            else:
                self._cond.notify_all()
            assert self.parties == 0
        finally:
            self._cond.release()


def main():
    barrier = Barrier(3)

    url = 'inproc://test'
    print('Play asynchronous ping-pong on %s' % url)
    asyncio.ensure_future(ping(url, barrier))
    asyncio.ensure_future(pong(url, barrier))

    asyncio.ensure_future(close_loop(barrier))

    loop = asyncio.get_event_loop()
    try:
        loop.run_forever()
    finally:
        loop.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
