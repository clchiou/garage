import g1.messaging.parts.subscribers
from g1.apps import parameters
from g1.apps import utils
from g1.asyncs.bases import queues
from g1.bases import labels
# For now these are just aliases.
from g1.messaging.parts.subscribers import make_subscriber_params

from .. import subscribers  # pylint: disable=relative-beyond-top-level

SUBSCRIBER_LABEL_NAMES = (
    # Output.
    'queue',
    # Private.
    ('subscriber', g1.messaging.parts.subscribers.SUBSCRIBER_LABEL_NAMES),
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
    utils.define_maker(
        make_queue,
        {
            'return': module_labels.queue,
        },
    )
    utils.define_maker(
        subscribers.make_subscriber,
        {
            'queue': module_labels.queue,
            'return': module_labels.subscriber.subscriber,
        },
    )
    g1.messaging.parts.subscribers.setup_subscriber(
        module_labels.subscriber,
        module_params,
    )


def make_queue():
    return queues.Queue(capacity=32)
