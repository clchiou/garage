"""Simple TCP echo server."""

import functools
import logging

import curio

from garage import apps
from garage import parameters
from garage import parts
from garage.asyncs import utils
from garage.partdefs.asyncs import servers


LOG = logging.getLogger(__name__)


PARAMS = parameters.get(__name__)
PARAMS.port = parameters.define(25000, 'set port')


@parts.register_maker
def make_server(
        graceful_exit: servers.PARTS.graceful_exit) -> servers.PARTS.server:
    return utils.serve(
        graceful_exit,
        functools.partial(utils.make_server_socket, ('', PARAMS.port.get())),
        handle,
        logger=LOG,
    )


async def handle(client_sock, client_addr):
    async with client_sock:
        stream = client_sock.as_stream()
        async for line in stream:
            await stream.write(line)
    LOG.info('close connection to: %s', client_addr)


@apps.with_prog('echo-server')
@apps.with_selected_makers({servers.PARTS.server: all})
def main(_, serve: servers.PARTS.serve):
    return 0 if curio.run(serve()) else 1


if __name__ == '__main__':
    apps.run(main)
