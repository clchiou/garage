import g1.asyncs.agents.parts
from g1.apps import asyncs
from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels

from ..pubsub import subscribers
from . import utils as parts_utils

SUBSCRIBER_LABEL_NAMES = (
    # Input.
    'subscriber',
    # Private.
    'subscriber_params',
)


def define_subscriber(module_path=None, **kwargs):
    module_path = module_path or subscribers.__name__
    module_labels = labels.make_labels(module_path, *SUBSCRIBER_LABEL_NAMES)
    setup_subscriber(
        module_labels,
        parameters.define(module_path, make_subscriber_params(**kwargs)),
    )
    return module_labels


def setup_subscriber(module_labels, module_params):
    utils.depend_parameter_for(module_labels.subscriber_params, module_params)
    utils.define_maker(
        make_agent,
        {
            'subscriber': module_labels.subscriber,
            'params': module_labels.subscriber_params,
        },
    )


def make_subscriber_params(url=None, recv_timeout=None):
    return parameters.Namespace(
        'configure subscriber',
        url=parameters.make_parameter(
            url, str, 'url that subscriber dials to'
        ),
        recv_timeout=parameters.Parameter(
            recv_timeout,
            type=(type(None), int, float),
            unit='seconds',
        ),
    )


def make_agent(
    exit_stack: asyncs.LABELS.exit_stack,
    subscriber,
    params,
    agent_queue: g1.asyncs.agents.parts.LABELS.agent_queue,
    shutdown_queue: g1.asyncs.agents.parts.LABELS.shutdown_queue,
):
    exit_stack.enter_context(subscriber)
    if params.recv_timeout.get() is not None:
        subscriber.socket.recv_timeout = parts_utils.to_milliseconds_int(
            params.recv_timeout.get()
        )
    subscriber.socket.dial(params.url.get())
    agent_queue.spawn(subscriber.serve)
    shutdown_queue.put_nonblocking(subscriber.shutdown)
