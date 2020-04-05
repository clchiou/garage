import g1.asyncs.agents.parts
from g1.apps import asyncs
from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels

from ..pubsub import publishers
from . import utils as parts_utils

PUBLISHER_LABEL_NAMES = (
    # Input.
    'publisher',
    # Private.
    'publisher_params',
)


def define_publisher(module_path=None, **kwargs):
    module_path = module_path or publishers.__name__
    module_labels = labels.make_labels(module_path, *PUBLISHER_LABEL_NAMES)
    setup_publisher(
        module_labels,
        parameters.define(module_path, make_publisher_params(**kwargs)),
    )
    return module_labels


def setup_publisher(module_labels, module_params):
    utils.depend_parameter_for(module_labels.publisher_params, module_params)
    utils.define_maker(
        make_agent,
        {
            'publisher': module_labels.publisher,
            'params': module_labels.publisher_params,
        },
    )


def make_publisher_params(url=None, send_timeout=None):
    return parameters.Namespace(
        'configure publisher',
        url=parameters.make_parameter(
            url, str, 'url that publisher listens on'
        ),
        send_timeout=parameters.Parameter(
            send_timeout,
            type=(type(None), int, float),
            unit='seconds',
        ),
    )


def make_agent(
    exit_stack: asyncs.LABELS.exit_stack,
    publisher,
    params,
    agent_queue: g1.asyncs.agents.parts.LABELS.agent_queue,
    shutdown_queue: g1.asyncs.agents.parts.LABELS.shutdown_queue,
):
    exit_stack.enter_context(publisher)
    if params.send_timeout.get() is not None:
        publisher.socket.send_timeout = parts_utils.to_milliseconds_int(
            params.send_timeout.get()
        )
    publisher.socket.listen(params.url.get())
    agent_queue.spawn(publisher.serve)
    shutdown_queue.put_nonblocking(publisher.shutdown)
