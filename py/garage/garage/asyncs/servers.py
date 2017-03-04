"""A simple root of supervisor tree and a generic container."""

___all__ = [
    'serve',
]

import logging
import os
import signal

import curio

from garage import asyncs
from garage.okay import OKAY, NOT_OKAY


LOG = logging.getLogger(__name__)


# The root node of the supervisor tree
async def serve(graceful_exit, graceful_period, make_server_funcs):
    okay = NOT_OKAY
    async with asyncs.TaskStack() as servers:
        LOG.info('start servers: pid=%d', os.getpid())
        for make_server in make_server_funcs:
            await servers.spawn(make_server())
        # Also spawn default signal handler
        await servers.spawn(signal_handler(graceful_exit, graceful_period))
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
