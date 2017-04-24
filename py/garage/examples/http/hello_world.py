#!/usr/bin/env python3

"""Demonstration of garage.http.legacy."""

from concurrent import futures
import functools

from garage import cli
from garage.components import ARGS
from garage.http import legacy
from garage.threads import actors
from garage.threads import queues


@actors.OneShotActor.from_func
def api_handler(request_queue):
    try:
        while True:
            request, response_future = request_queue.get()
            response_future.set_result('hello world')
    except queues.Closed:
        pass


@cli.command()
@cli.argument('--address', default='127.0.0.1',
              help="""set server address (default to %(default)s)""")
@cli.argument('--port', type=int, default=8080,
              help="""set server port (default to %(default)s)""")
@cli.argument('--certificate',
              help="""set HTTP server certificate""")
@cli.argument('--private-key',
              help="""set HTTP server private key""")
@cli.argument('--client-authentication', action='store_true',
              help="""enable client authentication""")
def hello_world(args: ARGS):

    request_queue = queues.Queue()

    if args.certificate and args.private_key:
        make_ssl_context = functools.partial(
            legacy.make_ssl_context,
            args.certificate,
            args.private_key,
            client_authentication=args.client_authentication,
        )
    else:
        make_ssl_context = None

    server = legacy.api_server(
        name='hello_world',
        address=(args.address, args.port),
        request_queue=request_queue, request_timeout=5,
        make_ssl_context=make_ssl_context,
    )
    handler = api_handler(request_queue)

    futs = [server._get_future(), handler._get_future()]
    try:
        for fut in futures.as_completed(futs):
            fut.result()
    except KeyboardInterrupt:
        request_queue.close()

    for fut in futures.as_completed(futs):
        fut.result()


if __name__ == '__main__':
    hello_world()
