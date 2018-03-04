"""Demonstration of garage.http.legacy.

Example of accessing the web service:
    curl -XPOST http://127.0.0.1:8080/
"""

from concurrent import futures
import functools

from garage import apps
from garage.http import legacy
from garage.threads import actors
from garage.threads import queues


@actors.OneShotActor.from_func
def api_handler(request_queue):
    try:
        while True:
            _, response_future = request_queue.get()
            response_future.set_result('hello world')
    except queues.Closed:
        pass


@apps.with_argument(
    '--address', default='127.0.0.1',
    help="""set server address (default to %(default)s)""")
@apps.with_argument(
    '--port', type=int, default=8080,
    help="""set server port (default to %(default)s)""")
@apps.with_argument(
    '--certificate', help="""set HTTP server certificate""")
@apps.with_argument(
    '--private-key', help="""set HTTP server private key""")
@apps.with_argument(
    '--client-authentication', action='store_true',
    help="""enable client authentication""")
def main(args):
    """Demonstration of garage.http.legacy."""

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

    return 0


if __name__ == '__main__':
    apps.run(main)
