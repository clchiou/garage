"""Demonstrate web server."""

from startup import startup

import g1.asyncs.agents.parts
import g1.webs.parts
from g1.apps import asyncs
from g1.asyncs import kernels

LABELS = g1.webs.parts.define_server(
    host='127.0.0.1',
    port=8000,
    reuse_address=True,
    reuse_port=True,
)


async def handler(request, response):
    del request  # Unused.
    response.status = 200
    response.headers['Content-Type'] = 'text/plain'
    response.commit()
    await response.write(b'Hello, world!')


startup.set(LABELS.handler, handler)


def main(supervise_agents: g1.asyncs.agents.parts.LABELS.supervise_agents):
    kernels.run(supervise_agents)
    return 0


if __name__ == '__main__':
    asyncs.run(main)
