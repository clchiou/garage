"""Calculator web service.

Example of accessing the web service:
    echo '{"operands": [1, 2, 3]}' | nghttp -v -d - http://127.0.0.1:8080/1/add
"""

import json
import logging

import http2

from garage import apps
from garage import parameters
from garage import parts
from garage.http import handlers
from garage.http import routers
from garage.http import servers
from garage.partdefs.asyncs import servers as asyncs_servers
from garage.partdefs.http import servers as http_servers


LOG = logging.getLogger(__name__)


PARTS = http_servers.create_parts(__name__)


PARAMS = parameters.define_namespace(
    __name__,
    namespace=http_servers.create_params(port=8080),
)


parts.define_maker(http_servers.create_maker(PARTS, PARAMS))


@parts.define_maker
def make_handler() -> PARTS.handler:
    router = routers.ApiRouter(name='calculator', version=1)
    router.add_handler('add', handlers.ApiEndpointHandler(
        endpoint_add,
        make_response_headers=make_response_headers,
        decode=decode_request, encode=encode_response,
    ))
    return servers.Server(router)


def make_response_headers(_):
    return [(b'content-type', b'application/json')]


def decode_request(_, body):
    if not body:
        raise servers.ClientError(
            http2.Status.BAD_REQUEST, message='empty request body')
    try:
        return json.loads(body.decode('utf8'))
    except Exception as cause:
        exc = servers.ClientError(
            http2.Status.BAD_REQUEST, message='incorrect encoding')
        raise exc from cause


def encode_response(_, obj):
    return json.dumps(obj).encode('utf8')


async def endpoint_add(request):
    try:
        return {'sum': sum(request['operands'])}
    except Exception as cause:
        exc = servers.ClientError(
            http2.Status.BAD_REQUEST,
            message='incorrect request',
            internal_message='incorrect request: %r' % request,
        )
        raise exc from cause


if __name__ == '__main__':
    apps.run(
        apps.App(asyncs_servers.main)
        .with_description('Calculator web service.')
        .with_input_parts({PARTS.logger: LOG})
    )
