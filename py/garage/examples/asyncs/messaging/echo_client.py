"""Sample NN_REQ client."""

import logging

import nanomsg as nn
from nanomsg.curio import Socket

from garage import apps
from garage import parameters
from garage import parts
from garage.asyncs import TaskStack
from garage.asyncs.futures import Future
from garage.asyncs.messaging import reqrep
from garage.asyncs.queues import Queue
from garage.partdefs.asyncs import servers


LOG = logging.getLogger(__name__)


PARAMS = parameters.define_namespace(__name__)
PARAMS.port = parameters.create(25000, 'set port')
PARAMS.message = parameters.create('', 'set message to send')


@parts.define_maker
async def echo_client(
    graceful_exit: servers.PARTS.graceful_exit,
    ) -> servers.PARTS.server:
    request = PARAMS.message.get().encode('utf8')
    LOG.info('connect to local TCP port: %d', PARAMS.port.get())
    async with Socket(protocol=nn.NN_REQ) as socket, TaskStack() as stack:
        socket.connect('tcp://127.0.0.1:%d' % PARAMS.port.get())
        queue = Queue()
        await stack.spawn(reqrep.client(graceful_exit, [socket], queue))
        async with Future() as response_future:
            await queue.put((request, response_future.promise()))
            response = await response_future.result()
        LOG.info('receive resposne: %r', response)


if __name__ == '__main__':
    apps.run(apps.App(servers.main).with_description(__doc__))
