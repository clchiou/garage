import g1.networks.servers.parts
from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels

from .. import servers  # pylint: disable=relative-beyond-top-level
from . import nghttp2

SERVER_LABEL_NAMES = (
    # Input.
    'application',
    # Private.
    ('server', g1.networks.servers.parts.SERVER_LABEL_NAMES),
)


def define_server(module_path=None, **kwargs):
    module_path = module_path or servers.__name__
    module_labels = labels.make_nested_labels(module_path, SERVER_LABEL_NAMES)
    setup_server(
        module_labels,
        parameters.define(module_path, make_server_params(**kwargs)),
    )
    return module_labels


def setup_server(module_labels, module_params):
    g1.networks.servers.parts.setup_server(module_labels.server, module_params)
    utils.define_maker(
        # Although this is called a server, from the perspective of
        # g1.networks.servers.SocketServer, this is a handler.
        servers.HttpServer,
        {
            'server_socket': module_labels.server.socket,
            'application': module_labels.application,
            'return': module_labels.server.handler,
        },
    )


def make_server_params(**kwargs):
    kwargs.setdefault('protocols', (nghttp2.NGHTTP2_PROTO_VERSION_ID, ))
    return g1.networks.servers.parts.make_server_params(**kwargs)
