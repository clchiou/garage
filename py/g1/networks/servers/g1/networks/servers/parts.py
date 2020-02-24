import collections.abc

import g1.asyncs.agents.parts
from g1.apps import asyncs
from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels

from .. import servers
from . import sockets

SERVER_LABEL_NAMES = (
    'params',
    # Server.
    'server',
    'handler',
    # Server socket.
    'socket',
    # SSL context.
    'ssl_context',
    'certificate',
    'private_key',
    'client_authentication',
    'protocols',
)


def define_server(module_path=None, **kwargs):
    module_path = module_path or servers.__name__
    module_labels = labels.make_labels(module_path, *SERVER_LABEL_NAMES)
    setup_server(
        module_labels,
        parameters.define(module_path, make_server_params(**kwargs)),
    )
    return module_labels


def setup_server(module_labels, module_params):
    # Server.
    utils.define_maker(
        servers.SocketServer,
        {
            'socket': module_labels.socket,
            'handler': module_labels.handler,
            'return': module_labels.server,
        },
    )
    utils.define_maker(
        make_agent,
        {
            'server': module_labels.server,
        },
    )
    # Server socket.
    utils.depend_parameter_for(module_labels.params, module_params)
    utils.define_maker(
        make_server_socket,
        {
            'params': module_labels.params,
            'ssl_context': module_labels.ssl_context,
            'return': module_labels.socket,
        },
    )
    # SSL context.
    for name in (
        'certificate',
        'private_key',
        'client_authentication',
        'protocols',
    ):
        utils.depend_parameter_for(module_labels[name], module_params[name])
    utils.define_maker(
        sockets.make_ssl_context,
        {
            'certificate': module_labels.certificate,
            'private_key': module_labels.private_key,
            'client_authentication': module_labels.client_authentication,
            'protocols': module_labels.protocols,
            'return': module_labels.ssl_context,
        },
    )


def make_server_params(
    *,
    host='',
    port=0,
    reuse_address=False,
    reuse_port=False,
    protocols=(),
):
    return parameters.Namespace(
        'make server socket',
        host=parameters.Parameter(host, type=str),
        port=parameters.Parameter(port, type=int),
        reuse_address=parameters.Parameter(reuse_address, type=bool),
        reuse_port=parameters.Parameter(reuse_port, type=bool),
        # SSL context.
        certificate=parameters.Parameter(''),
        private_key=parameters.Parameter(''),
        client_authentication=parameters.Parameter(False),
        protocols=parameters.Parameter(
            protocols, type=collections.abc.Iterable
        ),
    )


def make_agent(
    server,
    agent_queue: g1.asyncs.agents.parts.LABELS.agent_queue,
    shutdown_queue: g1.asyncs.agents.parts.LABELS.shutdown_queue,
):
    agent_queue.spawn(server.serve)
    shutdown_queue.put_nonblocking(server.shutdown)


def make_server_socket(
    exit_stack: asyncs.LABELS.exit_stack,
    params,
    ssl_context,
):
    return exit_stack.enter_context(
        sockets.make_server_socket(
            (params.host.get(), params.port.get()),
            reuse_address=params.reuse_address.get(),
            reuse_port=params.reuse_port.get(),
            ssl_context=ssl_context,
        ),
    )
