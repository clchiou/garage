"""Demonstrate a socket client."""

import socket
import sys

from g1.asyncs import kernels


async def request(port):
    with kernels.SocketAdapter(socket.socket()) as sock:
        await sock.connect(('127.0.0.1', port))
        await sock.send(b'Hello, World!\n')
        print('recv: %r' % await sock.recv(4096))


def main(argv):
    if len(argv) < 2:
        print('usage: %s port' % argv[0], file=sys.stderr)
        return 1
    kernels.run(request(int(argv[1])))
    return 0


if __name__ == '__main__':
    sys.exit(kernels.call_with_kernel(main, sys.argv))
