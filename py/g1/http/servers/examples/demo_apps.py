"""Demonstrate ``g1.apps``-based HTTP server."""

from startup import startup

from g1.apps import asyncs
from g1.asyncs import kernels

import g1.asyncs.servers.parts
import g1.http.servers.parts

LABELS = g1.http.servers.parts.define_http_server(
    host='127.0.0.1',
    port=8000,
    reuse_address=True,
    reuse_port=True,
)


async def application(environ, start_response):
    del environ  # Unused.
    start_response('200 OK', [('Content-Type', 'text/plain')])
    return [b'Hello, world!']


startup.set(LABELS.application, application)


def main(supervise_servers: g1.asyncs.servers.parts.LABELS.supervise_servers):
    kernels.run(supervise_servers)
    return 0


if __name__ == '__main__':
    asyncs.run(main)
