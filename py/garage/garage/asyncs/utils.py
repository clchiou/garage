__all__ = [
    'make_server_socket',
]

from curio import socket


async def make_server_socket(
        address, *,
        family=socket.AF_INET,
        backlog=128,
        reuse_address=True,
        reuse_port=False):
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        if reuse_address:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        if reuse_port:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
        sock.bind(address)
        sock.listen(backlog)
    except Exception:
        await sock.close()
        raise
    else:
        return sock
