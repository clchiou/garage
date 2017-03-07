"""Calculator web service."""

from functools import partial
import json
import logging

import curio

import http2

from garage import cli
from garage import components
from garage.asyncs.utils import make_server_socket, serve
from garage.http.handlers import ApiEndpointHandler
from garage.http.routers import ApiRouter
from garage.http.servers import ClientError, Server
from garage.startups.asyncs.servers import (
    GracefulExitComponent,
    ServerContainerComponent,
)


LOG = logging.getLogger('calculator_server')


class ServerComponent(components.Component):

    require = (components.ARGS, GracefulExitComponent.provide.graceful_exit)

    provide = ServerContainerComponent.require.make_server

    def add_arguments(self, parser):
        group = parser.add_argument_group(__name__)
        group.add_argument(
            '--port', default=8080, type=int,
            help="""set port (default to %(default)s)""")
        group.add_argument(
            '--certificate', help="""set HTTP/2 server certificate""")
        group.add_argument(
            '--private-key', help="""set HTTP/2 server private key""")
        group.add_argument(
            '--client-authentication', action='store_true',
            help="""enable client authentication""")

    def check_arguments(self, parser, args):
        if (args.certificate is None) != (args.private_key is None):
            parser.error('require both certificate and private key')

    def make(self, require):

        if require.args.certificate and require.args.private_key:
            make_ssl_context = partial(
                http2.make_ssl_context,
                require.args.certificate,
                require.args.private_key,
                client_authentication=require.args.client_authentication,
            )
        else:
            make_ssl_context = None

        router = ApiRouter(name='calculator', version=1)
        router.add_handler('add', ApiEndpointHandler(
            endpoint_add,
            make_response_headers=make_response_headers,
            decode=decode_request, encode=encode_response,
        ))

        return partial(
            serve,
            require.graceful_exit,
            partial(make_server_socket, ('', require.args.port)),
            Server(router),
            make_ssl_context=make_ssl_context,
            logger=LOG,
        )


def make_response_headers(request_headers):
    return [(b'content-type', b'application/json')]


def decode_request(headers, body):
    if not body:
        raise ClientError(
            http2.Status.BAD_REQUEST, message='empty request body')
    try:
        return json.loads(body.decode('utf8'))
    except Exception as cause:
        exc = ClientError(
            http2.Status.BAD_REQUEST, message='incorrect encoding')
        raise exc from cause


def encode_response(headers, obj):
    return json.dumps(obj).encode('utf8')


async def endpoint_add(request):
    try:
        return {'sum': sum(request['operands'])}
    except Exception as cause:
        exc = ClientError(
            http2.Status.BAD_REQUEST,
            message='incorrect request',
            internal_message='incorrect request: %r' % request,
        )
        raise exc from cause


@cli.command('calculator-server')
@cli.component(ServerContainerComponent)
@cli.component(ServerComponent)
def main(serve: ServerContainerComponent.provide.serve):
    return 0 if curio.run(serve()) else 1


if __name__ == '__main__':
    main()
