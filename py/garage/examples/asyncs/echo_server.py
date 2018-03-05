"""Simple TCP echo server."""

import functools
import logging

from garage import apps
from garage import parameters
from garage import parts
from garage.asyncs import utils
from garage.partdefs.asyncs import servers


LOG = logging.getLogger(__name__)


PARAMS = parameters.define_namespace(__name__)
PARAMS.port = parameters.create(25000, 'set port')


@parts.define_maker
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


if __name__ == '__main__':
    apps.run(apps.App(servers.main).with_description(__doc__))
