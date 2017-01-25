#!/usr/bin/env python3

import sys

import curio

from nanomsg.curio import Socket
import nanomsg as nn


async def server(url):
    async with Socket(protocol=nn.NN_REP) as sock, sock.bind(url):
        while True:
            message = await sock.recv()
            message_contents = bytes(message.as_memoryview())
            print('RECV: %r' % message_contents)
            await sock.send(message_contents)


def main(argv):
    if len(argv) < 2:
        print('Usage: %s url' % argv[0])
        print('  sample URL: tcp://127.0.0.1:25000')
        return 1
    curio.run(server(argv[1]))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
