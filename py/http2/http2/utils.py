__all__ = [
    'make_ssl_context',
]

import ssl


def make_ssl_context(crt, key):
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    ssl_context.load_cert_chain(crt, key)
    if ssl.HAS_ALPN:
        ssl_context.set_alpn_protocols(['h2'])
    else:
        asserts.precond(ssl.HAS_NPN)
        ssl_context.set_npn_protocols(['h2'])
    return ssl_context
