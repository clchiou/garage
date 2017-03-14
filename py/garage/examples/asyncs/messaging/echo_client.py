"""Sample NN_REQ client."""

from functools import partial
import logging

import curio

from nanomsg.curio import Socket
import nanomsg as nn

from garage import cli
from garage import components
from garage.asyncs import TaskStack
from garage.asyncs.futures import Future
from garage.asyncs.messaging import reqrep
from garage.asyncs.queues import Queue
from garage.startups.asyncs.servers import ServerContainerComponent


LOG = logging.getLogger(__name__)


class ClientComponent(components.Component):

    require = components.ARGS

    provide = ServerContainerComponent.require.make_server

    def add_arguments(self, parser):
        group = parser.add_argument_group(__name__)
        group.add_argument(
            '--port', type=int, default=25000,
            help="""set port (default to %(default)s)""")
        group.add_argument(
            'message', type=str,
            help="""set message contents""")

    def make(self, require):
        return partial(echo_client, require.args.port, require.args.message)


async def echo_client(port, message):
    request = message.encode('utf8')
    LOG.info('connect to local TCP port: %d', port)
    async with Socket(protocol=nn.NN_REQ) as socket, TaskStack() as stack:
        socket.connect('tcp://127.0.0.1:%d' % port)
        queue = Queue()
        await stack.spawn(reqrep.client(socket, queue))
        async with Future() as response_future:
            await queue.put((request, response_future.promise()))
            response = await response_future.result()
        LOG.info('receive resposne: %r', response)


@cli.command('echo-client')
@cli.component(ServerContainerComponent)
@cli.component(ClientComponent)
def main(serve: ServerContainerComponent.provide.serve):
    return 0 if curio.run(serve()) else 1


if __name__ == '__main__':
    main()
