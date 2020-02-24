"""Demonstrate socket server."""

from startup import startup

import g1.asyncs.agents.parts
import g1.networks.servers.parts
from g1.apps import asyncs
from g1.asyncs import kernels

LABELS = g1.networks.servers.parts.define_server(
    host='127.0.0.1',
    port=8000,
    reuse_address=True,
    reuse_port=True,
)


async def handler(socket, address):
    with socket:
        message = await socket.recv(64)
        print('receive %r from %s' % (message, address))
        await socket.send(message)


startup.set(LABELS.handler, handler)


def main(supervise_agents: g1.asyncs.agents.parts.LABELS.supervise_agents):
    kernels.run(supervise_agents)
    return 0


if __name__ == '__main__':
    asyncs.run(main)
