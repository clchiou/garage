"""Sample NN_REP server that echos requests."""

import logging

from nanomsg.curio import Socket
import nanomsg as nn

from garage import apps
from garage import parameters
from garage import parts
from garage.asyncs import TaskStack
from garage.asyncs.messaging import reqrep
from garage.asyncs.queues import Closed, Queue
from garage.partdefs.asyncs import servers


LOG = logging.getLogger(__name__)


PARAMS = parameters.define_namespace(__name__)
PARAMS.port = parameters.create(25000, 'set port')


@parts.define_maker
async def echo_server(
    graceful_exit: servers.PARTS.graceful_exit,
    ) -> servers.PARTS.server:
    LOG.info('serving at local TCP port: %d', PARAMS.port.get())
    socket = Socket(domain=nn.AF_SP_RAW, protocol=nn.NN_REP)
    async with socket, TaskStack() as stack:
        socket.bind('tcp://127.0.0.1:%d' % PARAMS.port.get())
        queue = Queue()
        await stack.spawn(reqrep.server(graceful_exit, socket, queue))
        while True:
            try:
                request, resposne_promise = await queue.get()
            except Closed:
                break
            LOG.info('receive request: %r', request)
            resposne_promise.set_result(request)


if __name__ == '__main__':
    apps.run(apps.App(servers.main).with_description(__doc__))
