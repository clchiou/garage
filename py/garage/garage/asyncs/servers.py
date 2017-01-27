"""A simple root of supervisor tree and a generic container."""

___all__ = [
    'SERVER_MAKER',
    'prepare',
]

import argparse
import logging
import os
import signal
from contextlib import ExitStack

import curio

from garage import asyncs
from garage import components
from garage.okay import OKAY, NOT_OKAY
from garage.startups.logging import LoggingComponent
from startup import Startup, startup


SERVER_MAKER = __name__ + ':server_maker'
SERVER_MAKERS = __name__ + ':server_makers'


LOG = logging.getLogger(__name__)


def prepare(*, prog=None, description, comps, verbose=1):
    parser = argparse.ArgumentParser(prog=prog, description=description)

    startup.set(components.MAIN, main)
    startup.set(components.PARSER, parser)
    startup(copy_first_stage_vars)

    next_startup = Startup()
    parser.set_defaults(next_startup=next_startup)

    # Overcome the limitation that startup requires >0 writes.
    next_startup.set(SERVER_MAKER, None)
    next_startup(collect_server_maker)

    # First-stage startup
    components.bind(LoggingComponent(verbose=verbose))

    # Second-stage startup
    for comp in components.find_closure(*comps):
        components.bind(comp, next_startup=next_startup)


def copy_first_stage_vars(args: components.ARGS, parser: components.PARSER):
    next_startup = args.next_startup
    next_startup.set(components.ARGS, args)
    next_startup.set(components.PARSER, parser)


def collect_server_maker(server_makers: [SERVER_MAKER]) -> SERVER_MAKERS:
    return tuple(filter(None, server_makers))


# The root node of the supervisor tree
async def init(server_makers):
    okay = NOT_OKAY
    async with asyncs.TaskStack() as servers:
        LOG.info('start servers: pid=%d', os.getpid())
        for server_maker in server_makers:
            await servers.spawn(server_maker())
        # Also spawn default signal handler
        await servers.spawn(signal_handler())
        # Now let's wait for the servers...
        async with curio.wait(servers) as wait_servers:
            # When one server exits, normally or not, we bring down all
            # other servers.
            server_task = await wait_servers.next_done()
            try:
                await server_task.join()
                LOG.info('server exit: %r', server_task)
                okay = OKAY
            except curio.TaskError:
                LOG.exception('server crash: %r', server_task)
            LOG.info('stop servers')
    LOG.info('exit')
    return okay


async def signal_handler():
    """Exit on SIGINT."""
    async with curio.SignalSet(signal.SIGINT) as sigset:
        LOG.info('receive signal: %s', await sigset.wait())


def main(args):
    with ExitStack() as exit_stack:
        next_startup = args.next_startup
        next_startup.set(components.EXIT_STACK, exit_stack)
        server_makers = next_startup.call()[SERVER_MAKERS]
        okay = curio.run(init(server_makers))
        return 0 if okay else 1
