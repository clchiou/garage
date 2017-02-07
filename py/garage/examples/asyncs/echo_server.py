"""Sample echo server."""

from functools import partial
import logging
import sys

from curio import socket

from garage import asyncs
from garage import components
from garage.asyncs.servers import GRACEFUL_EXIT, SERVER_MAKER, prepare


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
        return partial(echo_server, require.graceful_exit, require.args.port)


async def echo_server(graceful_exit, port):
    async with asyncs.TaskStack() as stack, asyncs.TaskSet() as tasks:
        listener_task = await stack.spawn(listener(port, tasks.spawn))
        joiner_task = await stack.spawn(joiner(tasks))
        await graceful_exit.wait()
        LOG.info('initiate graceful exit')
        await listener_task.cancel()
        tasks.graceful_exit()
        await joiner_task.join()


async def listener(port, spawn):
    async with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('127.0.0.1', port))
        sock.listen(8)
        LOG.info('serving at local TCP port: %d', port)
        while True:
            client_sock, client_addr = await sock.accept()
            await spawn(handler(client_sock, client_addr))


async def joiner(tasks):
    async for task in tasks:
        try:
            await task.join()
        except Exception:
            LOG.exception('handler crash')
        else:
            LOG.info('handler exit normally')


async def handler(client_sock, client_addr):
    LOG.info('receive connection from: %s', client_addr)
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
