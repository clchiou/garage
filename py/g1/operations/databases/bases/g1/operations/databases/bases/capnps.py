__all__ = [
    'LOADER',
    'PACKED_WIRE_DATA',
    'WIRE_DATA',
]

from pathlib import Path

import capnp

from g1.messaging.wiredata import capnps

from . import interfaces

LOADER = capnp.SchemaLoader()
LOADER.load_once((Path(__file__).parent / 'databases.schema').read_bytes())

WIRE_DATA = capnps.CapnpWireData(LOADER)
WIRE_DATA.register(interfaces.DatabaseRequest)
WIRE_DATA.register(interfaces.DatabaseResponse)

PACKED_WIRE_DATA = capnps.CapnpPackedWireData(LOADER)
PACKED_WIRE_DATA.register(interfaces.DatabaseRequest)
PACKED_WIRE_DATA.register(interfaces.DatabaseResponse)
