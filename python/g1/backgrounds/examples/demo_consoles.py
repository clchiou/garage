"""Demonstrate console over socket."""

import g1.backgrounds.consoles
from g1.apps import asyncs
from g1.asyncs import kernels

g1.backgrounds.consoles.define_console()


def main(supervise_agents: g1.asyncs.agents.parts.LABELS.supervise_agents):
    kernels.run(supervise_agents)
    return 0


if __name__ == '__main__':
    asyncs.run(main)
