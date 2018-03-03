"""Sample NN_REQ client."""

import logging

import curio

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


PARAMS = parameters.get(__name__)
PARAMS.port = parameters.define(25000, 'set port')
PARAMS.message = parameters.define('', 'set message to send')


@parts.register_maker
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


@apps.with_prog('echo-client')
@apps.with_selected_makers({servers.PARTS.server: all})
def main(_, serve: servers.PARTS.serve):
    return 0 if curio.run(serve()) else 1


if __name__ == '__main__':
    apps.run(main)
