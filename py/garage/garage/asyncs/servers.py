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
async def serve(graceful_exit, grace_period, make_server_funcs):

    okay = NOT_OKAY

    async with asyncs.TaskStack() as servers:

        LOG.info('start servers: pid=%d', os.getpid())
        for make_server in make_server_funcs:
            await servers.spawn(make_server())
        all_tasks = list(servers)

        # Also spawn default signal handler.
        signal_handler_task = await asyncs.spawn(
            signal_handler(graceful_exit, grace_period),
            daemon=True,
        )
        all_tasks.append(signal_handler_task)

        # When one server exits, normally or not, we bring down all
        # other servers.  But if it exits normally, we initiate a
        # graceful exit.
        server = await asyncs.select(all_tasks)
        if server is signal_handler_task:
            pass
        elif server.exception:
            LOG.error('server crash: %r', server, exc_info=server.exception)
        else:
            LOG.info('notify graceful exit')
            graceful_exit.set()
            async with curio.ignore_after(grace_period) as timeout:
                okay = await wait_servers(servers)
            if timeout.expired:
                LOG.info('exceed grace period %f', grace_period)

        # When we leave this block, TaskStack will cancel all the
        # remaining tasks.

    LOG.info('exit')
    return okay


async def wait_servers(servers):
    okay = OKAY
    for server in servers:
        await server.wait()
        okay &= not server.exception
        if server.exception:
            LOG.error('server crash: %r', server, exc_info=server.exception)
        else:
            LOG.info('server exit: %r', server)
    return okay


async def signal_handler(graceful_exit, grace_period):
    # Exploit the fact that when one of the server task exits, the init
    # task will bring down all other server tasks.
    async with curio.SignalQueue(signal.SIGINT, signal.SIGTERM) as sigqueue:
        sig = await sigqueue.get()
        LOG.info('receive signal: %s', sig)
        if sig == signal.SIGINT:
            LOG.info('notify graceful exit')
            graceful_exit.set()
        elif sig == signal.SIGTERM:
            return
        else:
            raise AssertionError('unknown signal: %s' % sig)
        async with curio.ignore_after(grace_period):
            sig = await sigqueue.get()
            LOG.info('receive signal again: %s', sig)
            return
        LOG.info('exceed grace period %f', grace_period)
