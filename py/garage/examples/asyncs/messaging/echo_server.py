"""Sample NN_REP server that echos requests."""

from functools import partial
import logging

import curio

from nanomsg.curio import Socket
import nanomsg as nn

from garage import cli
from garage import components
from garage.asyncs import TaskStack
from garage.asyncs.messaging import reqrep
from garage.asyncs.queues import Queue
from garage.startups.asyncs.servers import ServerContainerComponent


LOG = logging.getLogger(__name__)


class ServerComponent(components.Component):

    require = components.ARGS

    provide = ServerContainerComponent.require.make_server

    def add_arguments(self, parser):
        group = parser.add_argument_group(__name__)
        group.add_argument(
            '--port', default=25000, type=int,
            help="""set port (default to %(default)s)""")

    def make(self, require):
        return partial(echo_server, require.args.port)


async def echo_server(port):
    LOG.info('serving at local TCP port: %d', port)
    async with Socket(protocol=nn.NN_REP) as socket, TaskStack() as stack:
        socket.bind('tcp://127.0.0.1:%d' % port)
        queue = Queue()
        await stack.spawn(reqrep.server(socket, queue))
        while True:
            request, resposne_promise = await queue.get()
            LOG.info('receive request: %r', request)
            resposne_promise.set_result(request)


@cli.command('echo-server')
@cli.component(ServerContainerComponent)
@cli.component(ServerComponent)
def main(serve: ServerContainerComponent.provide.serve):
    return 0 if curio.run(serve()) else 1


if __name__ == '__main__':
    main()
