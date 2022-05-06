"""Wire data in Cap'n Proto format.

For now, users are expected to define ``dataclass`` to match Cap'n Proto
schema.  Hopefully this does not result in ``dataclass`` that are too
cumbersome to use.
"""

__all__ = [
    'CapnpPackedWireData',
    'CapnpWireData',
]

import capnp
from capnp import objects

from g1.bases.assertions import ASSERT

from .. import wiredata


class _BaseWireData(wiredata.WireData):

    # Subclass must overwrite these.
    _from_bytes = None
    _to_bytes = None

    def __init__(self, loader):
        self._loader = loader
        self._converters = {}

    def _get_converter(self, dataclass):
        key = '%s:%s' % (dataclass.__module__, dataclass.__qualname__)
        converter = self._converters.get(key)
        if converter is None:
            converter = self._converters[key] = objects.DataclassConverter(
                self._loader.struct_schemas[key],
                dataclass,
            )
        return converter

    def register(self, message_type):
        """Register message type (this is optional)."""
        ASSERT.predicate(message_type, wiredata.is_message_type)
        self._get_converter(message_type)

    def to_lower(self, message):
        ASSERT.predicate(message, wiredata.is_message)
        with capnp.MessageBuilder() as builder:
            self._get_converter(type(message)).to_message(message, builder)
            return self._to_bytes(builder)

    def to_upper(self, message_type, wire_message):
        ASSERT.predicate(message_type, wiredata.is_message_type)
        with self._from_bytes(wire_message) as reader:
            return self._get_converter(message_type).from_message(reader)


class CapnpWireData(_BaseWireData):

    _from_bytes = capnp.MessageReader.from_message_bytes
    _to_bytes = staticmethod(capnp.MessageBuilder.to_message_bytes)


class CapnpPackedWireData(_BaseWireData):

    _from_bytes = capnp.MessageReader.from_packed_message_bytes
    _to_bytes = staticmethod(capnp.MessageBuilder.to_packed_message_bytes)
