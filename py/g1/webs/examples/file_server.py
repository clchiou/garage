"""Serve files."""

from pathlib import Path

from startup import startup

import g1.webs.handlers.files
import g1.webs.handlers.responses
import g1.webs.parts
from g1.apps import asyncs
from g1.asyncs import kernels

LABELS = g1.webs.parts.define_web_app(
    host='127.0.0.1',
    port=8000,
    reuse_address=True,
    reuse_port=True,
)


@startup
def make_handler() -> LABELS.handler:
    return g1.webs.handlers.responses.Defaults(
        g1.webs.handlers.files.make_handler(Path.cwd()),
        [('Cache-Control', 'public, max-age=31536000')],
        [],
    )


def main(supervise_servers: g1.asyncs.servers.parts.LABELS.supervise_servers):
    kernels.run(supervise_servers)
    return 0


if __name__ == '__main__':
    asyncs.run(main)
