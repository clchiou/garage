"""Generic server container."""

__all__ = [
    'MAKE_SERVER',
    'SHUTDOWN',
    'LOOP',
    'prepare',
    # Server helpers.
    'tcp_server',
]

import argparse
import asyncio
import logging
import os
import signal
from contextlib import ExitStack

from garage import components
from garage.asyncs.processes import process
from garage.okay import OKAY, NOT_OKAY
from garage.startups.logging import LoggingComponent
from startup import Startup, startup


MAKE_SERVER = __name__ + ':make_server'
SERVER_MAKERS = __name__ + ':server_makers'


SHUTDOWN = __name__ + ':shutdown'
SHUTDOWN_CALLBACKS = __name__ + ':shutdown_callbacks'


LOOP = __name__ + ':loop'


LOG = logging.getLogger(__name__)


def prepare(*, prog=None, description, comps, verbose=1):
    parser = argparse.ArgumentParser(prog=prog, description=description)

    startup.set(LOOP, None)
    startup.set(components.MAIN, main)
    startup.set(components.PARSER, parser)
    startup(copy_first_stage_vars)

    next_startup = Startup()
    parser.set_defaults(next_startup=next_startup)

    # Overcome the limitation that startup requires >0 writes.
    next_startup.set(MAKE_SERVER, None)
    next_startup(collect_make_server)
    next_startup.set(SHUTDOWN, None)
    next_startup(collect_shutdown)

    # First-stage startup
    components.bind(LoggingComponent(verbose=verbose))

    # Second-stage startup
    for comp in components.find_closure(*comps, ignore=[LOOP]):
        components.bind(comp, next_startup=next_startup)


def copy_first_stage_vars(
        args: components.ARGS, parser: components.PARSER, loop: LOOP):
    next_startup = args.next_startup
    next_startup.set(components.ARGS, args)
    next_startup.set(components.PARSER, parser)
    if loop is None:
        LOG.debug('use default event loop')
        loop = asyncio.get_event_loop()
    next_startup.set(LOOP, loop)


def collect_make_server(server_makers: [MAKE_SERVER]) -> SERVER_MAKERS:
    return list(filter(None, server_makers))


def collect_shutdown(callbacks: [SHUTDOWN]) -> SHUTDOWN_CALLBACKS:
    return dict(filter(None, callbacks))


def main(args):
    with ExitStack() as exit_stack:
        next_startup = args.next_startup
        next_startup.set(components.EXIT_STACK, exit_stack)

        varz = next_startup.call()
        loop = varz[LOOP]

        LOG.info('start servers: pid=%d', os.getpid())
        servers = make_servers(
            varz[SERVER_MAKERS],
            varz[SHUTDOWN_CALLBACKS],
            loop,
        )

        del varz

        okay = OKAY
        try:
            # Run servers...
            done, pending = loop.run_until_complete(asyncio.wait(
                servers,
                return_when=asyncio.FIRST_EXCEPTION,
            ))
            okay &= check_servers(done)
            okay &= stop_servers(pending, timeout=10, loop=loop)

        except KeyboardInterrupt:
            LOG.info('graceful shutdown')
            okay &= stop_servers(servers, timeout=2, loop=loop)

        finally:
            loop.close()

        LOG.info('exit')
        return 0 if okay else 1


def make_servers(server_makers, callback_table, loop):
    servers = []
    callbacks = []
    for make_server in server_makers:
        server = make_server()
        servers.append(server)
        # By default, use server.stop to request shutdown.
        callbacks.append(callback_table.get(make_server, server.stop))
    loop.add_signal_handler(signal.SIGTERM, request_shutdown, callbacks)
    return servers


def request_shutdown(callbacks):
    LOG.info('shutdown')
    for callback in callbacks:
        callback()


def stop_servers(servers, *, timeout=None, loop=None):
    if not servers:
        return OKAY
    for server in servers:
        server.stop()
    done, pending = (loop or asyncio.get_event_loop()).run_until_complete(
        asyncio.wait(servers, timeout=timeout))
    okay = check_servers(done)
    for server in pending:
        LOG.error('server did not stop: %r', server)
        okay = NOT_OKAY
    return okay


def check_servers(servers):
    okay = OKAY
    for server in servers:
        if server.exception():
            LOG.error('server crashed: %r', server,
                      exc_info=server.exception())
            okay = NOT_OKAY
    return okay


### Server helpers.


@process
async def tcp_server(exit, create_server, *, name=None):
    """Wrap a TCP server in a process."""
    name = name or 'tcp_server'
    LOG.info('%s: create server', name)
    server = await create_server()
    LOG.info('%s: start serving', name)
    try:
        await exit
    finally:
        LOG.info('%s: stop server', name)
        server.close()  # This initiates graceful shutdown.
        try:
            await server.wait_closed()
        except Exception:
            LOG.exception('%s: err when closing server', name)
