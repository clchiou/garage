import g1.asyncs.agents.parts
from g1.apps import asyncs
from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels

from ..reqrep import servers

SERVER_LABEL_NAMES = (
    # Input.
    'server',
    # Private.
    'server_params',
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
    utils.depend_parameter_for(module_labels.server_params, module_params)
    utils.define_maker(
        make_agent,
        {
            'server': module_labels.server,
            'params': module_labels.server_params,
        },
    )


def make_server_params(url=None, parallelism=1):
    return parameters.Namespace(
        'configure messaging server',
        url=parameters.make_parameter(url, str, 'url that server listens on'),
        parallelism=parameters.Parameter(
            parallelism,
            'number of server tasks',
            type=int,
            validate=(0).__lt__,
        ),
    )


def make_agent(
    exit_stack: asyncs.LABELS.exit_stack,
    server,
    params,
    agent_queue: g1.asyncs.agents.parts.LABELS.agent_queue,
    shutdown_queue: g1.asyncs.agents.parts.LABELS.shutdown_queue,
):
    exit_stack.enter_context(server)
    server.socket.listen(params.url.get())
    for _ in range(params.parallelism.get()):
        agent_queue.spawn(server.serve)
    shutdown_queue.put_nonblocking(server.shutdown)
