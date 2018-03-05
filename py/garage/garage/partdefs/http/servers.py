import functools

import http2

import garage.asyncs.utils
import garage.http.servers
from garage import parameters
from garage import parts
from garage.partdefs.asyncs import servers


def create_parts(module_name):
    return parts.PartList(module_name, [
        ('handler', parts.AUTO),
        ('logger', parts.AUTO),
    ])


def create_params(*, host='', port=80):
    params = parameters.create_namespace('create async http(s) server')
    params.host = parameters.create(host, 'let server bind to this address')
    params.port = parameters.create(port, 'let server listen to this port')
    params.certificate = parameters.create('', 'set server TLS certificate')
    params.private_key = parameters.create('', 'set server TLS private key')
    params.enable_client_authentication = parameters.create(
        False, 'enable authenticate client certificate')
    return params


def create_maker(part_list, params):

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
