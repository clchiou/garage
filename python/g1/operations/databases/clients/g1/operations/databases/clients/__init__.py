__all__ = [
    'make_client',
]

import logging

from g1.messaging.reqrep import clients

from g1.operations.databases.bases import capnps
from g1.operations.databases.bases import interfaces

logging.getLogger(__name__).addHandler(logging.NullHandler())


def make_client():
    return clients.Client(
        interfaces.DatabaseRequest,
        interfaces.DatabaseResponse,
        capnps.WIRE_DATA,
    )
