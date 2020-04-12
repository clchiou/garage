__all__ = [
    'make_subscriber',
]

import logging

from g1.messaging.pubsub import subscribers

from g1.operations.databases.bases import capnps
from g1.operations.databases.bases import interfaces

logging.getLogger(__name__).addHandler(logging.NullHandler())


def make_subscriber(queue):
    return subscribers.Subscriber(
        interfaces.DatabaseEvent,
        queue,
        capnps.WIRE_DATA,
    )
