__all__ = [
    'DynamicObject',
]

from . import bases
from .schemas import Type
from .dynamics import DynamicEnum
from .dynamics import DynamicStruct


class DynamicObject:
    """Let you access DynamicStruct like a regular read-only object.

    At the moment we do not support setting attributes.
    """

    __annotations__ = {}

    def __init__(self, struct):
        assert isinstance(struct, (DynamicStruct, DynamicStruct.Builder))
        self._struct = struct

    def __getattr__(self, name):

        # Translate name.
        camel_case = bases.snake_to_lower_camel(name)

        try:
            field = self._struct.schema[camel_case]
        except KeyError:
            msg = '%s has no field %r' % (self._struct.schema, camel_case)
            raise AttributeError(msg) from None

        # Retrieve the attribute.
        try:
            value = self._struct[camel_case]
        except KeyError:
            # Return default value for this attribute.
            if field.type.kind is Type.Kind.LIST:
                return ()
            else:
                return None

        # Apply built-in conversion: DynamicEnum -> int.
        if isinstance(value, DynamicEnum):
            value = value.get()

        # Apply user-supplied conversion.
        value = self.__annotations__.get(name, lambda x: x)(value)

        return value

    def __str__(self):
        return str(self._struct)

    __repr__ = bases.repr_object
