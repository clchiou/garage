"""Simple echo server."""

from functools import partial
import logging

import curio

from garage import cli
from garage import components
from garage.asyncs.utils import make_server_socket, serve
from garage.startups.asyncs.servers import (
    GracefulExitComponent,
    ServerContainerComponent,
)


LOG = logging.getLogger(__name__)


class ServerComponent(components.Component):

    require = (components.ARGS, GracefulExitComponent.provide.graceful_exit)

    provide = ServerContainerComponent.require.make_server

    def add_arguments(self, parser):
        group = parser.add_argument_group(__name__)
        group.add_argument(
            '--port', default=25000, type=int,
            help="""set port (default to %(default)s)""")

    def make(self, require):
        return partial(
            serve,
            require.graceful_exit,
            partial(make_server_socket, ('', require.args.port)),
            handle,
            logger=LOG,
        )


async def handle(client_sock, client_addr):
    async with client_sock:
        stream = client_sock.as_stream()
        async for line in stream:
            await stream.write(line)
    LOG.info('close connection to: %s', client_addr)


@cli.command('echo-server')
@cli.component(ServerContainerComponent)
@cli.component(ServerComponent)
def main(serve: ServerContainerComponent.provide.serve):
    return 0 if curio.run(serve()) else 1


if __name__ == '__main__':
    main()
