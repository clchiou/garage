"""Calculator server using parts."""

from startup import startup

import g1.asyncs.agents.parts
import g1.messaging.parts.servers
from g1.apps import asyncs
from g1.asyncs import kernels

from examples import interfaces

LABELS = g1.messaging.parts.servers.define_server()

startup.add_func(interfaces.make_server, {'return': LABELS.server})


def main(supervise_agents: g1.asyncs.agents.parts.LABELS.supervise_agents):
    kernels.run(supervise_agents)
    return 0


if __name__ == '__main__':
    asyncs.run(main)
