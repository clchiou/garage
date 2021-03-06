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
async def serve(graceful_exit, grace_period, server_coros):

    okay = NOT_OKAY

    async with asyncs.TaskStack() as servers:

        LOG.info('start servers: pid=%d', os.getpid())
        for server_coro in server_coros:
            await servers.spawn(server_coro)
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
            if not graceful_exit.is_set():
                LOG.info('serve: notify graceful exit')
                graceful_exit.set()
            async with curio.ignore_after(grace_period) as timeout:
                okay = await wait_servers(servers)
            if timeout.expired:
                LOG.warning('serve: exceed grace period %f', grace_period)
                for server in servers:
                    if not server.terminated:
                        LOG.warning(
                            'serve: server is still running: %r', server)

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
            LOG.info('signal_handler: notify graceful exit')
            graceful_exit.set()
        elif sig == signal.SIGTERM:
            return
        else:
            raise AssertionError('unknown signal: %s' % sig)
        async with curio.ignore_after(grace_period):
            sig = await sigqueue.get()
            LOG.info('receive signal again: %s', sig)
            return
        LOG.warning('signal_handler: exceed grace period %f', grace_period)
