"""Serve files."""

from pathlib import Path

from startup import startup

import g1.asyncs.agents.parts
import g1.webs.handlers.composers
import g1.webs.handlers.files
import g1.webs.handlers.responses
import g1.webs.parts
from g1.apps import asyncs
from g1.asyncs import kernels

LABELS = g1.webs.parts.define_server(
    host='127.0.0.1',
    port=8000,
    reuse_address=True,
    reuse_port=True,
)


@startup
def make_handler() -> LABELS.handler:
    return g1.webs.handlers.composers.Chain([
        g1.webs.handlers.responses.Defaults([
            ('Cache-Control', 'public, max-age=31536000')
        ]),
        g1.webs.handlers.files.make_dir_handler(Path.cwd()),
    ])


def main(supervise_agents: g1.asyncs.agents.parts.LABELS.supervise_agents):
    kernels.run(supervise_agents)
    return 0


if __name__ == '__main__':
    asyncs.run(main)
