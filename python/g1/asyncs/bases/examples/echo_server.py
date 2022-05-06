"""Demonstrate a socket server."""

import socket
import sys

from g1.asyncs import kernels
from g1.asyncs.bases import adapters


async def serve(port):
    with adapters.SocketAdapter(socket.socket()) as server_sock:
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
        server_sock.bind(('127.0.0.1', port))
        server_sock.listen()
        sock, addr = await server_sock.accept()
        print('accept: %r' % (addr, ))
        await handle(sock)


async def handle(sock):
    with sock:
        data = await sock.recv(4096)
        print('recv: %r' % data)
        await sock.send(data)


def main(argv):
    if len(argv) < 2:
        print('usage: %s port' % argv[0], file=sys.stderr)
        return 1
    kernels.run(serve(int(argv[1])))
    return 0


if __name__ == '__main__':
    sys.exit(kernels.call_with_kernel(main, sys.argv))
