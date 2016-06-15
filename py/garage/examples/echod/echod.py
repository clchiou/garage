"""A simple echo service."""

import argparse
import asyncio
import json
import logging
import sys

from garage.asyncs.futures import one_completed
from garage.asyncs.processes import ProcessOwner, process
from garage.asyncs.utils import CircuitBreaker, tcp_server
from http2 import Protocol


NAME = 'echod'


LOG = logging.getLogger(NAME)
LOG.addHandler(logging.NullHandler())


@process
async def echo_service(exit, port):

    def create_handler():
        return Protocol(lambda: echo)

    def create_server():
        loop = asyncio.get_event_loop()
        return loop.create_server(create_handler, port=port)

    async with ProcessOwner() as server:
        breaker = CircuitBreaker(count=4, period=60)
        while True:
            server.own(tcp_server(create_server))
            proc = await one_completed([], [server.proc, exit])
            try:
                await proc
            except Exception:
                LOG.exception('http server has crashed')
            if not breaker.count(raises=False):
                LOG.warning('circuit breaker is disconnected')
                return
            await server.disown()


async def echo(request, response):
    LOG.info(
        '%s %s',
        request.headers[b':method'].decode('ascii'),
        request.headers[b':path'].decode('ascii'),
    )
    data = {
        'headers': {
            name.decode('ascii'): value.decode('ascii')
            for name, value in request.headers.items()
        },
        'body': repr(await request.body),
    }
    response.headers[b':status'] = b'200'
    await response.write(json.dumps(data).encode('ascii'))
    response.close()


def main(argv):
    parser = argparse.ArgumentParser(prog=NAME, description=__doc__)
    parser.add_argument(
        '--port', type=int, default=8080,
        help="""port to listen on (default to %(default)s)""")
    args = parser.parse_args(argv[1:])

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )

    LOG.info('start')
    loop = asyncio.get_event_loop()
    procs = [
        echo_service(args.port),
    ]

    try:
        LOG.info('run services')
        done, _ = loop.run_until_complete(
            asyncio.wait(procs, return_when=asyncio.FIRST_EXCEPTION))
        for proc in done:
            proc.result()

    except KeyboardInterrupt:
        LOG.info('graceful shutdown')
        for proc in procs:
            proc.stop()
        done, _ = loop.run_until_complete(asyncio.wait(procs))
        for proc in done:
            if proc.exception():
                LOG.error('error in service %r',
                          proc, exc_info=proc.exception())

    except Exception:
        LOG.exception('non-graceful shutdown')

    finally:
        loop.close()

    LOG.info('exit')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
