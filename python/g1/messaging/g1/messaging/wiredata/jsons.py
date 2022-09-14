"""Wire data in JSON format.

This is good for fast prototyping but should not be used in production
as, for now, it lacks crucial features needed in protocol evolution.

For ease of use, this module does not require you to provide wire data
metadata, such as (stable) "wire names" of Python types or enum members.
Instead, it directly outputs names of Python types and enum members in
wire messages, which makes protocol evolution quite hard as any name
change will require a careful coordination of rolling out.
"""

__all__ = [
    'JsonWireData',
]

import base64
import dataclasses
import datetime
import enum
import json
import sys

from g1.bases import typings
from g1.bases.assertions import ASSERT

from .. import wiredata

# Python 3.7 supports parsing ISO 8601 (bpo-15873), finally!
ASSERT.greater_or_equal(sys.version_info, (3, 7))

NoneType = type(None)

_DIRECTLY_SERIALIZABLE_TYPES = (
    dict, list, tuple, str, int, float, bool, NoneType
)


class JsonWireData(wiredata.WireData):
    """JSON wire data converter.

    This supports ``datetime.datetime``, ``enum.Enum``, ``Exception``,
    ``typing.Tuple``, ``typing.List``, ``typing.Set``,
    ``typing.FrozenSet``, and ``typing.Union``.

    In addition, this supports ``typing.Dict``, which ``capnps`` does
    not support natively.  Be careful when you switching from ``jsons``
    to ``capnps``.

    Caveats:

    * This only supports simple exceptions; they are exceptions that can
      be initialized from another's ``args`` field data, and those data
      only contains direct serializable values.

    * The conversion is not language agnostic.  The wire data can be
      decoded more easily if the other side is also running Python.

    * For now the conversion is fairly simple and unoptimized.  It does
      not even check if a message value equals to its default and omits
      it from output entirely.
    """

    def to_lower(self, message):
        ASSERT.predicate(message, wiredata.is_message)
        raw_message = self._encode_value(type(message), message)
        return json.dumps(raw_message).encode('ascii')

    def to_upper(self, message_type, wire_message):
        ASSERT.predicate(message_type, wiredata.is_message_type)
        raw_message = json.loads(wire_message)
        return self._decode_raw_value(message_type, raw_message)

    def _encode_value(self, value_type, value):
        """Encode a value into a raw value.

        This and ``_decode_raw_value`` complement each other.
        """

        if typings.is_recursive_type(value_type):

            if value_type.__origin__ in (list, set, frozenset):
                element_type = value_type.__args__[0]
                return [
                    self._encode_value(element_type, element)
                    for element in value
                ]

            elif value_type.__origin__ is tuple:
                ASSERT.equal(len(value), len(value_type.__args__))
                return tuple(
                    self._encode_value(element_type, element)
                    for element_type, element in zip(
                        value_type.__args__,
                        value,
                    )
                )

            elif value_type.__origin__ is dict:
                # JSON keys must be string-typed.
                ASSERT.issubclass(value_type.__args__[0], str)
                return {
                    self._encode_value(value_type.__args__[0], pair[0]):
                    self._encode_value(value_type.__args__[1], pair[1])
                    for pair in value.items()
                }

            elif typings.is_union_type(value_type):

                # Make a special case for ``None``.
                if value is None:
                    ASSERT.in_(NoneType, value_type.__args__)
                    return None

                # Make a special case for ``Optional[T]``.
                type_ = typings.match_optional_type(value_type)
                if type_:
                    return self._encode_value(type_, value)

                for type_ in value_type.__args__:
                    if typings.is_recursive_type(type_):
                        if _match_recursive_type(type_, value):
                            return {
                                str(type_): self._encode_value(type_, value)
                            }
                    elif isinstance(value, type_):
                        return {
                            type_.__name__: self._encode_value(type_, value)
                        }

                return ASSERT.unreachable(
                    'value is not any union element type: {!r} {!r}',
                    value_type,
                    value,
                )

            else:
                return ASSERT.unreachable(
                    'unsupported generic: {!r}', value_type
                )

        elif wiredata.is_message(value):
            ASSERT.predicate(value_type, wiredata.is_message_type)
            return {
                f.name: self._encode_value(f.type, getattr(value, f.name))
                for f in dataclasses.fields(value)
            }

        elif isinstance(value, datetime.datetime):
            ASSERT.issubclass(value_type, datetime.datetime)
            return value.isoformat()

        elif isinstance(value, enum.Enum):
            ASSERT.issubclass(value_type, enum.Enum)
            return value.name

        # JSON does not support binary type; so it has to be encoded.
        elif isinstance(value, bytes):
            ASSERT.issubclass(value_type, bytes)
            return base64.standard_b64encode(value).decode('ascii')

        elif isinstance(value, Exception):
            ASSERT.issubclass(value_type, Exception)
            return {
                type(value).__name__: [
                    ASSERT.isinstance(arg, _DIRECTLY_SERIALIZABLE_TYPES)
                    for arg in value.args
                ]
            }

        elif isinstance(value, _DIRECTLY_SERIALIZABLE_TYPES):
            ASSERT.issubclass(value_type, _DIRECTLY_SERIALIZABLE_TYPES)
            return value

        else:
            return ASSERT.unreachable(
                'unsupported value type: {!r} {!r}', value_type, value
            )

    def _decode_raw_value(self, value_type, raw_value):
        """Decode a raw value into ``value_type``-typed value.

        This and ``_encode_value`` complement each other.
        """

        if typings.is_recursive_type(value_type):

            if value_type.__origin__ in (list, set, frozenset):
                element_type = value_type.__args__[0]
                return value_type.__origin__(
                    self._decode_raw_value(element_type, raw_element)
                    for raw_element in raw_value
                )

            elif value_type.__origin__ is tuple:
                ASSERT.equal(len(raw_value), len(value_type.__args__))
                return tuple(
                    self._decode_raw_value(element_type, raw_element)
                    for element_type, raw_element in zip(
                        value_type.__args__,
                        raw_value,
                    )
                )

            elif value_type.__origin__ is dict:
                # JSON keys must be string-typed.
                ASSERT.issubclass(value_type.__args__[0], str)
                return {
                    self._decode_raw_value(value_type.__args__[0], pair[0]):
                    self._decode_raw_value(value_type.__args__[1], pair[1])
                    for pair in raw_value.items()
                }

            elif typings.is_union_type(value_type):

                # Handle ``None`` special case.
                if raw_value is None:
                    ASSERT.in_(NoneType, value_type.__args__)
                    return None

                # Handle ``Optional[T]`` special case.
                type_ = typings.match_optional_type(value_type)
                if type_:
                    return self._decode_raw_value(type_, raw_value)

                ASSERT.equal(len(raw_value), 1)
                type_name, raw_element = next(iter(raw_value.items()))
                for type_ in value_type.__args__:
                    if typings.is_recursive_type(type_):
                        candidate = str(type_)
                    else:
                        candidate = type_.__name__
                    if type_name == candidate:
                        return self._decode_raw_value(type_, raw_element)

                return ASSERT.unreachable(
                    'raw value is not any union element type: {!r} {!r}',
                    value_type,
                    raw_value,
                )

            else:
                return ASSERT.unreachable(
                    'unsupported generic: {!r}', value_type
                )

        elif wiredata.is_message_type(value_type):
            return value_type(
                **{
                    f.name: self._decode_raw_value(f.type, raw_value[f.name])
                    for f in dataclasses.fields(value_type)
                    if f.name in raw_value
                }
            )

        elif not isinstance(value_type, type):
            # Non-``type`` instance cannot be passed to ``issubclass``.
            return ASSERT.unreachable(
                'unsupported value type: {!r}', value_type
            )

        elif issubclass(value_type, datetime.datetime):
            return value_type.fromisoformat(raw_value)

        elif issubclass(value_type, enum.Enum):
            return value_type[raw_value]

        elif issubclass(value_type, bytes):
            return base64.standard_b64decode(raw_value.encode('ascii'))

        elif issubclass(value_type, Exception):
            ASSERT.equal(len(raw_value), 1)
            return value_type(
                *(
                    ASSERT.isinstance(raw_arg, _DIRECTLY_SERIALIZABLE_TYPES)
                    for raw_arg in raw_value[value_type.__name__]
                )
            )

        elif issubclass(value_type, _DIRECTLY_SERIALIZABLE_TYPES):
            if value_type in _DIRECTLY_SERIALIZABLE_TYPES:
                return ASSERT.isinstance(raw_value, value_type)
            else:
                # Support sub-type of int, etc.
                return value_type(raw_value)

        else:
            return ASSERT.unreachable(
                'unsupported value type: {!r}', value_type
            )


def _match_recursive_type(type_, value):

    if not typings.is_recursive_type(type_):
        # Base case of the recursive type.
        return isinstance(value, type_)

    elif type_.__origin__ in (list, set, frozenset):
        return (
            isinstance(value, type_.__origin__) and
            all(_match_recursive_type(type_.__args__[0], v) for v in value)
        )

    elif type_.__origin__ is tuple:
        return (
            isinstance(value, tuple) and \
            len(value) == len(type_.__args__) and
            all(_match_recursive_type(t, v)
                for t, v in zip(type_.__args__, value))
        )

    elif type_.__origin__ is dict:
        return (
            isinstance(value, dict) and all(
                _match_recursive_type(type_.__args__[0], k)
                and _match_recursive_type(type_.__args__[1], v)
                for k, v in value.items()
            )
        )

    elif typings.is_union_type(type_):
        return any(_match_recursive_type(t, value) for t in type_.__args__)

    else:
        return False
