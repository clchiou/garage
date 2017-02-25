__all__ = [
    'make_server_socket',
]

from curio import socket


def make_server_socket(
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
        # XXX: I would prefer a non-async make_server_socket and that
        # forbids me calling sock.close() here bucause it's async; so I
        # have to call the underlying socket object's close() directly.
        # Since no one else is referencing to this sock object, this
        # hack should be fine.
        sock._socket.close()
        raise
    else:
        return sock
