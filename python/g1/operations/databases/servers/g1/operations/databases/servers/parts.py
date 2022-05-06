import g1.asyncs.agents.parts
import g1.databases.parts
import g1.messaging.parts.publishers
import g1.messaging.parts.servers
from g1.apps import asyncs
from g1.apps import parameters
from g1.apps import utils
from g1.asyncs.bases import queues
from g1.bases import labels
from g1.messaging.pubsub import publishers
from g1.messaging.reqrep import servers as g1_servers

from g1.operations.databases.bases import capnps
from g1.operations.databases.bases import interfaces

from . import servers

SERVER_LABEL_NAMES = (
    # Private.
    ('server', g1.messaging.parts.servers.SERVER_LABEL_NAMES),
    ('publisher', g1.messaging.parts.publishers.PUBLISHER_LABEL_NAMES),
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
            'publisher': module_labels.publisher.publisher,
            'return': module_labels.server.server,
        },
    )
    utils.define_maker(
        make_publisher,
        {
            'return': module_labels.publisher.publisher,
        },
    )
    g1.messaging.parts.servers.setup_server(
        module_labels.server,
        module_params.server,
    )
    g1.messaging.parts.publishers.setup_publisher(
        module_labels.publisher,
        module_params.publisher,
    )
    g1.databases.parts.setup_create_engine(
        module_labels.database,
        module_params.database,
    )


def make_server_params(**kwargs):
    kwargs.setdefault('url', 'tcp://0.0.0.0:%d' % interfaces.DATABASE_PORT)
    kwargs.setdefault('parallelism', 16)
    publisher_url = kwargs.pop(
        'publisher_url',
        'tcp://0.0.0.0:%d' % interfaces.DATABASE_PUBLISHER_PORT,
    )
    return parameters.Namespace(
        server=g1.messaging.parts.servers.make_server_params(**kwargs),
        publisher=g1.messaging.parts.publishers.make_publisher_params(
            url=publisher_url,
        ),
        database=g1.databases.parts.make_create_engine_params(
            dialect='sqlite',
        ),
    )


def make_server(
    exit_stack: asyncs.LABELS.exit_stack,
    create_engine,
    publisher,
    agent_queue: g1.asyncs.agents.parts.LABELS.agent_queue,
    shutdown_queue: g1.asyncs.agents.parts.LABELS.shutdown_queue,
):
    server = exit_stack.enter_context(
        servers.DatabaseServer(engine=create_engine(), publisher=publisher)
    )
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


def make_publisher():
    return publishers.Publisher(queues.Queue(capacity=32), capnps.WIRE_DATA)
