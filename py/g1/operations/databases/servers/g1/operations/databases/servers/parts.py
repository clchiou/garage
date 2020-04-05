import g1.asyncs.agents.parts
import g1.databases.parts
import g1.messaging.parts.servers
from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels
from g1.messaging.reqrep import servers as g1_servers

from g1.operations.databases.bases import capnps
from g1.operations.databases.bases import interfaces

from . import servers

SERVER_LABEL_NAMES = (
    # Private.
    ('server', g1.messaging.parts.servers.SERVER_LABEL_NAMES),
    ('database', g1.databases.parts.DATABASE_LABEL_NAMES),
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
    utils.define_maker(
        make_server,
        {
            'create_engine': module_labels.database.create_engine,
            'return': module_labels.server.server,
        },
    )
    g1.messaging.parts.servers.setup_server(
        module_labels.server,
        module_params.server,
    )
    g1.databases.parts.setup_create_engine(
        module_labels.database,
        module_params.database,
    )


def make_server_params(**kwargs):
    kwargs.setdefault('url', 'tcp://0.0.0.0:%d' % interfaces.DATABASE_PORT)
    kwargs.setdefault('parallelism', 16)
    return parameters.Namespace(
        server=g1.messaging.parts.servers.make_server_params(**kwargs),
        database=g1.databases.parts.make_create_engine_params(
            dialect='sqlite',
        ),
    )


def make_server(
    create_engine,
    agent_queue: g1.asyncs.agents.parts.LABELS.agent_queue,
    shutdown_queue: g1.asyncs.agents.parts.LABELS.shutdown_queue,
):
    server = servers.DatabaseServer(engine=create_engine())
    agent_queue.spawn(server.serve)
    shutdown_queue.put_nonblocking(server.shutdown)
    return g1_servers.Server(
        server,
        interfaces.DatabaseRequest,
        interfaces.DatabaseResponse,
        capnps.WIRE_DATA,
        warning_level_exc_types=(
            interfaces.InvalidRequestError,
            interfaces.KeyNotFoundError,
            interfaces.LeaseNotFoundError,
            interfaces.TransactionNotFoundError,
            interfaces.TransactionTimeoutError,
        ),
        invalid_request_error=interfaces.InvalidRequestError(),
        internal_server_error=interfaces.InternalError(),
    )
