"""A server that does nothing."""

import logging

import curio

from garage import apps
from garage import parts
from garage.partdefs.asyncs import servers


LOG = logging.getLogger(__name__)


@parts.register_maker
async def dummy_server() -> servers.PARTS.server:
    try:
        duration = 10
        LOG.info('sleep for %d seconds and then exit...', duration)
        await curio.sleep(duration)
    finally:
        LOG.info('main_server: exit')


@apps.with_selected_makers({servers.PARTS.server: all})
def main(_, serve: servers.PARTS.serve):
    return 0 if curio.run(serve()) else 1


if __name__ == '__main__':
    apps.run(main)
