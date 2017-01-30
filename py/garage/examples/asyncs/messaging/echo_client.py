"""Sample NN_REQ client."""

from functools import partial
import logging
import sys

from nanomsg.curio import Socket
import nanomsg as nn

from garage import components
from garage.asyncs import TaskStack
from garage.asyncs.futures import Future
from garage.asyncs.messaging import reqrep
from garage.asyncs.queues import Queue
from garage.asyncs.servers import SERVER_MAKER, prepare


LOG = logging.getLogger(__name__)


class ClientComponent(components.Component):

    require = components.ARGS

    provide = SERVER_MAKER

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
    async with TaskStack() as stack, Socket(protocol=nn.NN_REQ) as socket:
        socket.connect('tcp://127.0.0.1:%d' % port)
        queue = Queue()
        await stack.spawn(reqrep.client(socket, queue))
        async with Future() as response_future:
            await queue.put((request, response_future.make_promise()))
            response = await response_future.get_result()
        LOG.info('receive resposne: %r', response)


def main(argv):
    prepare(
        description=__doc__,
        comps=[
            ClientComponent(),
        ],
    )
    return components.main(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
