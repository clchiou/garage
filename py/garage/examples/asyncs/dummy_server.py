"""A server that does nothing."""

import logging

import curio

from garage import cli
from garage import components
from garage.startups.asyncs.servers import ServerContainerComponent


LOG = logging.getLogger(__name__)


class ServerComponent(components.Component):

    provide = ServerContainerComponent.require.make_server

    def make(self, require):
        return dummy_server


async def dummy_server():
    try:
        duration = 10
        LOG.info('sleep for %d seconds and then exit...', duration)
        await curio.sleep(duration)
    finally:
        LOG.info('main_server: exit')


@cli.command('dummy-server')
@cli.component(ServerContainerComponent)
@cli.component(ServerComponent)
def main(serve: ServerContainerComponent.provide.serve):
    return 0 if curio.run(serve()) else 1


if __name__ == '__main__':
    main()
