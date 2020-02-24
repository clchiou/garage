__all__ = [
    'make_server_socket',
    'make_ssl_context',
]

import socket
import ssl

from g1.asyncs.bases import adapters


def make_server_socket(
    address,
    *,
    family=socket.AF_INET,
    backlog=128,
    reuse_address=False,
    reuse_port=False,
    ssl_context=None,
):
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, reuse_address)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, reuse_port)
        sock.bind(address)
        sock.listen(backlog)
        if ssl_context:
            sock = ssl_context.wrap_socket(sock, server_side=True)
    except Exception:
        sock.close()
        raise
    return adapters.SocketAdapter(sock)


def make_ssl_context(
    certificate,
    private_key,
    client_authentication=False,
    protocols=(),
):
    if not certificate or not private_key:
        return None
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(certificate, private_key)
    if client_authentication:
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.load_verify_locations(cafile=certificate)
    if protocols:
        if ssl.HAS_ALPN:
            ssl_context.set_alpn_protocols(protocols)
        if ssl.HAS_NPN:
            ssl_context.set_npn_protocols(protocols)
    return ssl_context
