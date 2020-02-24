import g1.asyncs.agents.parts
import g1.http.servers.parts
from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels
# For now this is just an alias.
from g1.http.servers.parts import make_server_params

from . import wsgi_apps

SERVER_LABEL_NAMES = (
    'handler',
    ('server', g1.http.servers.parts.SERVER_LABEL_NAMES),
)


def define_server(module_path=None, **kwargs):
    module_path = module_path or __package__
    module_labels = labels.make_nested_labels(module_path, SERVER_LABEL_NAMES)
    setup_server(
        module_labels,
        parameters.define(module_path, make_server_params(**kwargs)),
    )
    return module_labels


def setup_server(module_labels, module_params):
    g1.http.servers.parts.setup_server(module_labels.server, module_params)
    utils.define_maker(
        wsgi_apps.Application,
        {
            'handler': module_labels.handler,
            'return': module_labels.server.application,
        },
    )
    utils.define_maker(
        make_agent,
        {
            'application': module_labels.server.application,
        },
    )


def make_agent(
    application,
    agent_queue: g1.asyncs.agents.parts.LABELS.agent_queue,
    shutdown_queue: g1.asyncs.agents.parts.LABELS.shutdown_queue,
):
    agent_queue.spawn(application.serve)
    shutdown_queue.put_nonblocking(application.shutdown)
