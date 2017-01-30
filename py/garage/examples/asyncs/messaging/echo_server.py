"""Sample NN_REP server that echos requests."""

from functools import partial
import logging
import sys

from nanomsg.curio import Socket
import nanomsg as nn

from garage import components
from garage.asyncs import TaskStack
from garage.asyncs.messaging import reqrep
from garage.asyncs.queues import Queue
from garage.asyncs.servers import SERVER_MAKER, prepare


LOG = logging.getLogger(__name__)


class ServerComponent(components.Component):

    require = components.ARGS

    provide = SERVER_MAKER

    def add_arguments(self, parser):
        group = parser.add_argument_group(__name__)
        group.add_argument(
            '--port', default=25000, type=int,
            help="""set port (default to %(default)s)""")

    def make(self, require):
        return partial(echo_server, require.args.port)


async def echo_server(port):
    LOG.info('serving at local TCP port: %d', port)
    async with TaskStack() as stack, Socket(protocol=nn.NN_REP) as socket:
        socket.bind('tcp://127.0.0.1:%d' % port)
        queue = Queue()
        await stack.spawn(reqrep.server(socket, queue))
        while True:
            request, resposne_promise = await queue.get()
            LOG.info('receive request: %r', request)
            await resposne_promise.set_result(request)


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
