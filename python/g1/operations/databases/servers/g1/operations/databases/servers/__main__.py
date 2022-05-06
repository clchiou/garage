import g1.asyncs.agents.parts
from g1.apps import asyncs
from g1.asyncs import kernels

from . import parts

parts.define_server()


def main(supervise_agents: g1.asyncs.agents.parts.LABELS.supervise_agents):
    """Database server."""
    kernels.run(supervise_agents)
    return 0


if __name__ == '__main__':
    asyncs.run(main)
