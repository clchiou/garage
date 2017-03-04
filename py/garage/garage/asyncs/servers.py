"""A simple root of supervisor tree and a generic container."""

___all__ = [
    'GRACEFUL_EXIT',
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


GRACEFUL_EXIT = __name__ + ':graceful_exit'
GRACEFUL_PERIOD = 5  # Unit: seconds


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

    next_startup.set(GRACEFUL_EXIT, curio.Event())

    # Overcome the limitation that startup requires >0 writes.
    next_startup.set(SERVER_MAKER, None)
    next_startup(collect_server_maker)

    # First-stage startup
    components.bind(LoggingComponent(verbose=verbose))

    # Second-stage startup
    for comp in components.find_closure(*comps, ignore=[GRACEFUL_EXIT]):
        components.bind(comp, next_startup=next_startup)


def copy_first_stage_vars(args: components.ARGS, parser: components.PARSER):
    next_startup = args.next_startup
    next_startup.set(components.ARGS, args)
    next_startup.set(components.PARSER, parser)


def collect_server_maker(server_makers: [SERVER_MAKER]) -> SERVER_MAKERS:
    return tuple(filter(None, server_makers))


# The root node of the supervisor tree
async def init(graceful_exit, server_makers):
    okay = NOT_OKAY
    async with asyncs.TaskStack() as servers:
        LOG.info('start servers: pid=%d', os.getpid())
        for server_maker in server_makers:
            await servers.spawn(server_maker())
        # Also spawn default signal handler
        await servers.spawn(signal_handler(graceful_exit, GRACEFUL_PERIOD))
        # Now let's wait for the servers...
        server_task = await curio.wait(servers).next_done()
        # When one server exits, normally or not, we bring down all
        # other servers
        try:
            await server_task.join()
            LOG.info('server exit: %r', server_task)
            okay = OKAY
        except curio.TaskError:
            LOG.exception('server crash: %r', server_task)
        LOG.info('stop servers')
        # TaskStack will cancel all the remaining tasks
    LOG.info('exit')
    return okay


async def signal_handler(graceful_exit, graceful_period):
    # Exploit the fact that when one of the server task exits, the init
    # task will bring down all other server tasks
    async with curio.SignalSet(signal.SIGINT, signal.SIGTERM) as sigset:
        sig = await sigset.wait()
        LOG.info('receive signal: %s', sig)
        if sig is signal.SIGINT:
            LOG.info('notify graceful exit')
            await graceful_exit.set()
        elif sig is signal.SIGTERM:
            return
        else:
            raise AssertionError('unknown signal: %s' % sig)
        async with curio.ignore_after(graceful_period):
            sig = await sigset.wait()
            LOG.info('receive signal again: %s', sig)
            return
        LOG.info('exceed graceful period %f', graceful_period)


def main(args):
    with ExitStack() as exit_stack:
        next_startup = args.next_startup
        next_startup.set(components.EXIT_STACK, exit_stack)
        varz = next_startup.call()
        graceful_exit = varz[GRACEFUL_EXIT]
        server_makers = varz[SERVER_MAKERS]
        del varz
        okay = curio.run(init(graceful_exit, server_makers))
        return 0 if okay else 1
