"""Demonstrate web server."""

from startup import startup

from g1.apps import asyncs
from g1.asyncs import kernels

import g1.webs.parts

LABELS = g1.webs.parts.define_web_app(
    host='127.0.0.1',
    port=8000,
    reuse_address=True,
    reuse_port=True,
)


async def handler(request, response):
    del request  # Unused.
    response.status = 200
    response.headers['Content-Type'] = 'text/plain'
    response.write_nonblocking(b'Hello, world!')


startup.set(LABELS.handler, handler)


def main(supervise_servers: g1.asyncs.servers.parts.LABELS.supervise_servers):
    kernels.run(supervise_servers)
    return 0


if __name__ == '__main__':
    asyncs.run(main)
