import ssl

from g1.apps import asyncs
from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels

import g1.asyncs.servers.parts
import g1.networks.servers.parts

from .. import servers
from .nghttp2 import NGHTTP2_PROTO_VERSION_ID

HTTP_SERVER_LABEL_NAMES = (
    'server_socket_params',
    'server_socket',
    'application',
)


def define_http_server(module_path=None, **kwargs):
    """Define a HTTP server under ``module_path``."""
    module_path = module_path or servers.__name__
    module_labels = labels.make_labels(module_path, *HTTP_SERVER_LABEL_NAMES)
    setup_http_server(
        module_labels,
        parameters.define(
            module_path,
            make_server_socket_params(**kwargs),
        ),
    )
    return module_labels


def setup_http_server(module_labels, module_params):
    utils.depend_parameter_for(
        module_labels.server_socket_params, module_params
    )
    utils.define_maker(
        make_server_socket,
        {
            'params': module_labels.server_socket_params,
            'return': module_labels.server_socket,
        },
    )
    utils.define_binder(
        servers.serve_http,
        g1.asyncs.servers.parts.LABELS.serve,
        {
            'server_socket': module_labels.server_socket,
            'application': module_labels.application,
        },
    )
    utils.define_binder(
        on_graceful_exit,
        g1.asyncs.servers.parts.LABELS.serve,
        {
            'server_socket': module_labels.server_socket,
        },
    )


async def on_graceful_exit(
    graceful_exit: g1.asyncs.servers.parts.LABELS.graceful_exit,
    server_socket,
):
    await graceful_exit.wait()
    server_socket.close()


def make_server_socket_params(**kwargs):
    params = g1.networks.servers.parts.make_server_socket_params(**kwargs)
    return parameters.Namespace(
        'make HTTP server socket',
        **params._entries,
        **make_ssl_context_params()._entries,
    )


def make_server_socket(
    exit_stack: asyncs.LABELS.exit_stack,
    params,
):
    return g1.networks.servers.parts.make_server_socket(
        exit_stack,
        params,
        make_ssl_context(params),
    )


def make_ssl_context_params():
    return parameters.Namespace(
        'make SSL context for an HTTPS server',
        certificate=parameters.Parameter(''),
        private_key=parameters.Parameter(''),
        client_authentication=parameters.Parameter(False),
    )


def make_ssl_context(params):
    certificate = params.certificate.get()
    private_key = params.private_key.get()
    if not certificate or not private_key:
        return None
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(certificate, private_key)
    if params.client_authentication.get():
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.load_verify_locations(cafile=certificate)
    if ssl.HAS_ALPN:
        ssl_context.set_alpn_protocols([NGHTTP2_PROTO_VERSION_ID])
    if ssl.HAS_NPN:
        ssl_context.set_npn_protocols([NGHTTP2_PROTO_VERSION_ID])
    return ssl_context
