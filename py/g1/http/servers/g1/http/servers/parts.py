from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels

import g1.networks.servers.parts
# For now this is just an alias.
from g1.networks.servers.parts import make_server_params

from .. import servers
from . import nghttp2

SERVER_LABEL_NAMES = (
    'application',
    ('server', g1.networks.servers.parts.SERVER_LABEL_NAMES),
)


def define_server(module_path=None, **kwargs):
    module_path = module_path or servers.__name__
    kwargs.setdefault('protocols', (nghttp2.NGHTTP2_PROTO_VERSION_ID, ))
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
