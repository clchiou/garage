"""Convert application messages to/from wire data.

We are leveraging ``dataclasses`` module for message schema.
"""

__all__ = [
    # Public interface.
    'WireData',
    # Message type predicates.
    'is_message',
    'is_message_type',
]

import dataclasses


class WireData:
    """WireData interface.

    The data conversions are named ``to_upper`` and ``to_lower`` since
    conventionally a protocol stack diagram is drawn from top to bottom.
    """

    def to_lower(self, message):
        raise NotImplementedError

    def to_upper(self, message_type, wire_message):
        raise NotImplementedError


def is_message_type(message_type):
    return (
        dataclasses.is_dataclass(message_type)
        and isinstance(message_type, type)
    )


def is_message(message):
    return dataclasses.is_dataclass(message) and not isinstance(message, type)
