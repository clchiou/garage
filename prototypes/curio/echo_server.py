#!/usr/bin/env python3

import sys

import curio
import curio.socket


async def server(address):
    sock = curio.socket.socket(curio.socket.AF_INET, curio.socket.SOCK_STREAM)
    sock.setsockopt(curio.socket.SOL_SOCKET, curio.socket.SO_REUSEADDR, 1)
    sock.bind(address)
    sock.listen(5)
    print('Listen at', address)
    async with sock:
        while True:
            conn, addr = await sock.accept()
            await curio.spawn(handler(conn, addr))


async def handler(conn, address):
    print('Connection from', address)
    async with conn:
        while True:
            data = await conn.recv(256)
            if not data:
                break
            await conn.sendall(data)
    print('Connection closed')


def main(argv):
    curio.run(server(('', 25000)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
