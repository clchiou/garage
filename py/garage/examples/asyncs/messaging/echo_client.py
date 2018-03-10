"""Sample NN_REQ client."""

import logging

from garage import apps
from garage import parameters
from garage import parts
from garage.asyncs import futures
from garage.partdefs.asyncs import servers
from garage.partdefs.asyncs.messaging import reqrep


LOG = logging.getLogger(__name__)


PARTS = reqrep.create_client_parts(__name__)


PARAMS = parameters.define_namespace(__name__)
PARAMS.message = parameters.create('', 'set message to send')
PARAMS.echo_client = reqrep.create_client_params(
    connect=('tcp://127.0.0.1:25000',))


parts.define_maker(reqrep.create_client_maker(PARTS, PARAMS.echo_client))


@parts.define_maker
async def echo_client(queue: PARTS.request_queue) -> servers.PARTS.server:
    request = PARAMS.message.get().encode('utf8')
    async with futures.Future() as response_future:
        await queue.put((request, response_future.promise()))
        response = await response_future.result()
    LOG.info('receive resposne: %r', response)


if __name__ == '__main__':
    apps.run(apps.App(servers.main).with_description(__doc__))
