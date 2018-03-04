import functools

import http2

import garage.asyncs.utils
import garage.http.servers
from garage import parameters
from garage import parts
from garage.partdefs.asyncs import servers


def define_parts(module_name):
    return parts.PartList(module_name, [
        ('handler', parts.AUTO),
        ('logger', parts.AUTO),
    ])


def define_params(*, host='', port=80):
    params = parameters.define_namespace('create async http(s) server')
    params.host = parameters.define(host, 'let server bind to this address')
    params.port = parameters.define(port, 'let server listen to this port')
    params.certificate = parameters.define('', 'set server TLS certificate')
    params.private_key = parameters.define('', 'set server TLS private key')
    params.enable_client_authentication = parameters.define(
        False, 'enable authenticate client certificate')
    return params


def define_maker(part_list, params):

    def make_server(
            graceful_exit: servers.PARTS.graceful_exit,
            handler: part_list.handler,
            logger: part_list.logger,
        ) -> servers.PARTS.server:

        make_server_socket = functools.partial(
            garage.asyncs.utils.make_server_socket,
            address=(params.host.get(), params.port.get()),
        )

        certificate = params.certificate.get()
        private_key = params.private_key.get()
        client_authentication = params.enable_client_authentication.get()
        if certificate and private_key:
            make_ssl_context = functools.partial(
                http2.make_ssl_context,
                certificate,
                private_key,
                client_authentication=client_authentication,
            )
        else:
            make_ssl_context = None

        return garage.asyncs.utils.serve(
            graceful_exit,
            make_server_socket,
            handler,
            make_ssl_context=make_ssl_context,
            logger=logger,
        )

    return make_server
