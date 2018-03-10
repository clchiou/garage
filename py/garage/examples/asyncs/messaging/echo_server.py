"""Sample NN_REP server that echos requests."""

import logging

from garage import apps
from garage import parameters
from garage import parts
from garage.asyncs import queues
from garage.partdefs.asyncs import servers
from garage.partdefs.asyncs.messaging import reqrep


LOG = logging.getLogger(__name__)


PARTS = reqrep.create_server_parts(__name__)


PARAMS = parameters.define_namespace(
    __name__,
    namespace=reqrep.create_server_params(
        bind=('tcp://127.0.0.1:25000',),
    ),
)


parts.define_maker(reqrep.create_server_maker(PARTS, PARAMS))


@parts.define_maker
async def echo_server(queue: PARTS.request_queue) -> servers.PARTS.server:
    while True:
        try:
            request, resposne_promise = await queue.get()
        except queues.Closed:
            break
        LOG.info('receive request: %r', request)
        resposne_promise.set_result(request)


if __name__ == '__main__':
    apps.run(apps.App(servers.main).with_description(__doc__))
