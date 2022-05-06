"""Stream large amount of random data to client."""

import os

from startup import startup

import g1.asyncs.agents.parts
import g1.http.http1_servers.parts
from g1.apps import asyncs
from g1.asyncs import kernels

LABELS = g1.http.http1_servers.parts.define_server(
    host='127.0.0.1',
    port=8000,
    reuse_address=True,
    reuse_port=True,
)

_RESPONSE_SIZE = 1024 * 1024 * 1024  # 1 GB.
_CHUNK_SIZE = 65536  # 64 KB.


async def application(environ, start_response):
    del environ  # Unused.
    start_response(
        '200 OK',
        [('Content-Length', '%d' % _RESPONSE_SIZE)],
    )
    return random_output()


async def random_output():
    for _ in range(_RESPONSE_SIZE // _CHUNK_SIZE):
        yield os.urandom(_CHUNK_SIZE)
    remainder = _RESPONSE_SIZE % _CHUNK_SIZE
    if remainder > 0:
        yield os.urandom(remainder)


startup.set(LABELS.application, application)


def main(supervise_agents: g1.asyncs.agents.parts.LABELS.supervise_agents):
    kernels.run(supervise_agents)
    return 0


if __name__ == '__main__':
    asyncs.run(main)
