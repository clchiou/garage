#!/usr/bin/env python3

import curio

from nanomsg.curio import Socket
import nanomsg as nn


async def ping(url, ack):
    async with Socket(protocol=nn.NN_PUSH) as sock, sock.connect(url):
        await sock.send(b'Hello, World!')
        # Shutdown the endpoint after the other side ack'ed; otherwise
        # the message could be lost.
        await ack.wait()


async def pong(url, ack):
    async with Socket(protocol=nn.NN_PULL) as sock, sock.bind(url):
        message = await sock.recv()
        print(bytes(message.as_memoryview()).decode('ascii'))
        await ack.set()


async def main():
    ack = curio.Event()
    url = 'inproc://test'
    ping_task = await curio.spawn(ping(url, ack))
    pong_task = await curio.spawn(pong(url, ack))
    print('Waiting...')
    await ping_task.join()
    await pong_task.join()
    print('Completed')


if __name__ == '__main__':
    curio.run(main())
