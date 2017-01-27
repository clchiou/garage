"""A server that does nothing."""

import logging
import signal
import sys

import curio

from garage import components
from garage.asyncs.servers import SERVER_MAKER, prepare


LOG = logging.getLogger(__name__)


class ServerComponent(components.Component):

    provide = SERVER_MAKER

    def __init__(self, coro_func):
        self.coro_func = coro_func

    def make(self, _):
        return self.coro_func


async def main_server():
    try:
        duration = 10
        LOG.info('sleep for %d seconds and then exit...', duration)
        await curio.sleep(duration)
    finally:
        LOG.info('main_server: exit')


async def signal_handler():
    try:
        async with curio.SignalSet(signal.SIGINT) as sigset:
            sig = await sigset.wait()
            LOG.info('receive signal: %s', sig)
    finally:
        LOG.info('signal_handler: exit')


def main(argv):
    prepare(
        description=__doc__,
        comps=[
            ServerComponent(main_server),
            ServerComponent(signal_handler),
        ],
    )
    return components.main(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
