"""Generic 2-stage startup for launching services.

A service is just a convenient name for long-running async process.
"""

__all__ = [
    'MAKE_SERVICE',
    'prepare',
]

import argparse
import asyncio
import logging
from contextlib import ExitStack

from garage import components
from garage.asyncs.executors import WorkerPoolAdapter
from garage.threads.executors import WorkerPool
from startup import Startup, startup

from garage.startups.logging import LoggingComponent

from . import LOOP


MAKE_SERVICE = __name__ + ':make_service'
SERVICE_MAKERS = __name__ + ':service_makers'


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
    next_startup.set(MAKE_SERVICE, None)
    next_startup(collect_make_service)

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


def collect_make_service(service_makers: [MAKE_SERVICE]) -> SERVICE_MAKERS:
    return list(filter(None, service_makers))


def main(args):
    with ExitStack() as exit_stack:
        next_startup = args.next_startup
        next_startup.set(components.EXIT_STACK, exit_stack)

        varz = next_startup.call()
        loop = varz[LOOP]
        service_makers = varz[SERVICE_MAKERS]
        del varz

        services = [make_service() for make_service in service_makers]
        try:
            LOG.info('run services')
            done, _ = loop.run_until_complete(
                asyncio.wait(services, return_when=asyncio.FIRST_EXCEPTION))
            for service in done:
                service.result()

        except KeyboardInterrupt:
            LOG.info('graceful shutdown')
            for service in services:
                service.stop()
            done, _ = loop.run_until_complete(asyncio.wait(services))
            for service in done:
                if service.exception():
                    LOG.error('error in service %r', service,
                              exc_info=service.exception())

        except Exception:
            LOG.exception('non-graceful shutdown')

        finally:
            loop.close()

        LOG.info('exit')
        return 0
