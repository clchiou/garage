"""Sample echo server."""

from functools import partial
import logging
import sys

from curio import socket

from garage import asyncs
from garage import components
from garage.asyncs.servers import GRACEFUL_EXIT, SERVER_MAKER, prepare
from garage.asyncs.utils import make_server_socket, serve


LOG = logging.getLogger(__name__)


class ServerComponent(components.Component):

    require = (components.ARGS, GRACEFUL_EXIT)

    provide = SERVER_MAKER

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


def main(argv):
    prepare(
        description=__doc__,
        comps=[
            ServerComponent(),
        ],
    )
    return components.main(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
