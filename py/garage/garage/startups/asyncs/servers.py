"""Generic server container."""

__all__ = [
    'MAKE_SERVER',
    'GRACEFUL_SHUTDOWN',
    'prepare',
]

import argparse
import asyncio
import logging
import os
import signal
from contextlib import ExitStack

from garage import components
from garage.startups.logging import LoggingComponent
from startup import Startup, startup

from . import LOOP


MAKE_SERVER = __name__ + ':make_server'
SERVER_MAKERS = __name__ + ':server_makers'


GRACEFUL_SHUTDOWN = __name__ + ':graceful_shutdown'


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
    next_startup.set(GRACEFUL_SHUTDOWN, None)
    next_startup(register_graceful_shutdown)

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


def register_graceful_shutdown(callbacks: [GRACEFUL_SHUTDOWN]):
    callbacks = list(filter(None, callbacks))
    if not callbacks:
        # Don't use SIG_IGN because we want to log a message.
        signal.signal(signal.SIGQUIT, lambda *_: LOG.info('ignore SIGQUIT'))
        return
    def sigquit(*_):
        LOG.info('request graceful shutdown')
        for callback in callbacks:
            callback()
    signal.signal(signal.SIGQUIT, sigquit)


def main(args):
    with ExitStack() as exit_stack:
        next_startup = args.next_startup
        next_startup.set(components.EXIT_STACK, exit_stack)

        varz = next_startup.call()
        loop = varz[LOOP]
        server_makers = varz[SERVER_MAKERS]
        del varz

        LOG.info('start servers: pid=%d', os.getpid())
        servers = [make_server() for make_server in server_makers]
        try:
            done, pending = loop.run_until_complete(asyncio.wait(
                servers,
                return_when=asyncio.FIRST_EXCEPTION,
            ))
            check_servers(done)
            stop_servers(pending, timeout=10, loop=loop)

        except KeyboardInterrupt:
            LOG.info('shutdown')
            stop_servers(servers, timeout=2, loop=loop)

        finally:
            loop.close()

        LOG.info('exit')
        return 0


def stop_servers(servers, *, timeout=None, loop=None):
    if not servers:
        return
    for server in servers:
        server.stop()
    done, pending = (loop or asyncio.get_event_loop()).run_until_complete(
        asyncio.wait(servers, timeout=timeout))
    check_servers(done)
    for server in pending:
        LOG.error('server did not stop: %r', server)


def check_servers(servers):
    for server in servers:
        if server.exception():
            LOG.error('server crashed: %r', server,
                      exc_info=server.exception())
