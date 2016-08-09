"""Generic 2-stage startup for launching servers.

A server is just a convenient name for long-running async process.
"""

__all__ = [
    'MAKE_SERVER',
    'prepare',
]

import argparse
import asyncio
import logging
from contextlib import ExitStack

from garage import components
from garage.startups.logging import LoggingComponent
from startup import Startup, startup

from . import LOOP


MAKE_SERVER = __name__ + ':make_server'
SERVER_MAKERS = __name__ + ':server_makers'


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


def main(args):
    with ExitStack() as exit_stack:
        next_startup = args.next_startup
        next_startup.set(components.EXIT_STACK, exit_stack)

        varz = next_startup.call()
        loop = varz[LOOP]
        server_makers = varz[SERVER_MAKERS]
        del varz

        servers = [make_server() for make_server in server_makers]
        try:
            LOG.info('run servers')
            done, _ = loop.run_until_complete(
                asyncio.wait(servers, return_when=asyncio.FIRST_EXCEPTION))
            for server in done:
                server.result()

        except KeyboardInterrupt:
            LOG.info('graceful shutdown')
            for server in servers:
                server.stop()
            done, _ = loop.run_until_complete(asyncio.wait(servers))
            for server in done:
                if server.exception():
                    LOG.error('error in server %r', server,
                              exc_info=server.exception())

        except Exception:
            LOG.exception('non-graceful shutdown')

        finally:
            loop.close()

        LOG.info('exit')
        return 0
