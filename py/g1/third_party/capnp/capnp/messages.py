__all__ = [
    'MessageReader',
    'MessageBuilder',
]

from g1.bases.assertions import ASSERT

from . import _capnp
# pylint: disable=c-extension-no-member

from . import bases
from . import dynamics
from . import schemas


class _Array(bases.BaseResource):

    _raw_type = (_capnp._Array_byte, _capnp._Array_word)

    @property
    def memory_view(self):
        return self._raw.asBytes()


class MessageReader(bases.BaseResource):

    _raw_type = (_capnp.FlatArrayMessageReader, _capnp.PackedMessageReader)

    @classmethod
    def from_message_bytes(cls, message_bytes):
        return cls(_capnp.FlatArrayMessageReader(message_bytes), message_bytes)

    @classmethod
    def from_packed_message_bytes(cls, packed_message_bytes):
        return cls(
            _capnp.makePackedMessageReader(packed_message_bytes),
            packed_message_bytes,
        )

    def __init__(self, raw, message_bytes):
        super().__init__(raw)
        # Own ``message_bytes`` because ``FlatArrayMessageReader`` does
        # not own it.
        self._message_bytes = message_bytes

    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self._message_bytes = None

    def get_root(self, struct_schema):
        ASSERT.isinstance(struct_schema, schemas.StructSchema)
        return dynamics.DynamicStructReader(
            struct_schema,
            self._raw.getRoot(struct_schema._raw),
        )

    is_canonical = bases.def_f0(_capnp.MessageReader.isCanonical)


class MessageBuilder(bases.BaseResource):

    _raw_type = _capnp.MallocMessageBuilder

    @classmethod
    def from_message_bytes(cls, message_bytes):
        builder = cls()
        _capnp.initMessageBuilderFromFlatArrayCopy(message_bytes, builder._raw)
        return builder

    @classmethod
    def from_packed_message_bytes(cls, packed_message_bytes):
        builder = cls()
        _capnp.initMessageBuilderFromPackedArrayCopy(
            packed_message_bytes,
            builder._raw,
        )
        return builder

    def __init__(self):
        super().__init__(self._raw_type())

    to_message = bases.def_f0(_Array, _capnp.messageToFlatArray)
    to_packed_message = bases.def_f0(_Array, _capnp.messageToPackedArray)

    def to_message_bytes(self):
        with self.to_message() as array:
            return bytes(array.memory_view)

    def to_packed_message_bytes(self):
        with self.to_packed_message() as array:
            return bytes(array.memory_view)

    def set_root(self, struct):
        ASSERT.isinstance(struct, dynamics.DynamicStructReader)
        self._raw.setRoot(struct._raw)

    def get_root(self, struct_schema):
        ASSERT.isinstance(struct_schema, schemas.StructSchema)
        return dynamics.DynamicStructBuilder(
            struct_schema,
            self._raw.getRoot(struct_schema._raw),
        )

    def init_root(self, struct_schema):
        ASSERT.isinstance(struct_schema, schemas.StructSchema)
        return dynamics.DynamicStructBuilder(
            struct_schema,
            self._raw.initRoot(struct_schema._raw),
        )

    is_canonical = bases.def_f0(_raw_type.isCanonical)
