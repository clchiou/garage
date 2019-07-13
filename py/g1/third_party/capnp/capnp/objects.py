"""Converter for dataclass and struct.

The first version of converter is designed to be automatic, in the sense
that no additional annotation is required in neither capnp schema nor
dataclass definition, and the converter will derive the mapping between
the two automatically.  The drawback is that the converter will not
be able to derive the mapping for any kinds of dataclass definition; if
this drawback turns out to be too costly, we will revise the design.

Secondly, capnp-specific type, e.g., VOID-type, is generally hidden from
external users.  The drawback is that interface of union fields could
sometimes be quite confusing.

This could be confusing that the semantics of setting None to union vs
non-union fields is different:

* For union fields:

  * Setting None to a field is ignored, even if it is VOID-typed.
  * To select a VOID-typed field, you have to set VOID to it.

* For non-union fields:

  * Setting None to Pointer-typed fields will clear them.  Pointer types
    include: Text, Data, List(T), and struct.  Note that group and named
    union are considered struct type in this case.
  * Other field types except NoneType do not accept None.

The converter supports these Python types in additional to dataclass:
Exception, datetime, and enum.

Below is the type conversion table (note that unfortunately entries of
this table is not mutually exclusive):

--------------  -----------------------------------
capnp type      Python type
--------------  -----------------------------------
Void            NoneType
Void            VoidType
Bool            bool
IntX            int
UintX           int
Int32, Int64    datetime.datetime
Uint32, Uint64  datetime.datetime
FloatX          float
Float64         datetime.datetime
Text            str
Data            bytes
List(T)         typing.List[T]
enum            enum.Enum
struct, group   dataclass
struct, group   typing.Tuple[...]
struct, group   Exception
union           typing.Optional[F] for every member
named union     typing.Union[...]
--------------  -----------------------------------

* When a union is mapped to a typing.Union annotation, union member type
  must not be duplicate (and so there can a unique mapping).
* When mapping a struct to a dataclass, we sort struct fields by code
  order, which is more semantically relevant than ordinal number.
"""

__all__ = [
    'DataclassConverter',
]

import dataclasses
import datetime
import enum
import functools
import logging
import operator
import threading
import re

from g1.bases import assertions
from g1.bases import datetimes
from g1.bases import typings
from g1.bases.assertions import ASSERT

from . import _capnp
# pylint: disable=c-extension-no-member
from . import dynamics
from . import schemas

LOG = logging.getLogger(__name__)

NoneType = type(None)

TYPE_ASSERT = assertions.Assertions(lambda message, *_: TypeError(message))


class DataclassConverter:
    """Convert a dataclass object to/from a struct builder/reader."""

    def __init__(self, schema, dataclass):
        self._schema = ASSERT.isinstance(schema, schemas.StructSchema)
        self._dataclass = ASSERT.predicate(dataclass, is_dataclass)
        self._converter = _StructConverter.get(self._schema, self._dataclass)

    def from_reader(self, reader):
        ASSERT.is_(reader.schema, self._schema)
        return self._converter.from_reader(reader)

    def to_builder(self, dataobject, builder):
        ASSERT.isinstance(dataobject, self._dataclass)
        ASSERT.is_(builder.schema, self._schema)
        self._converter.to_builder(dataobject, builder)

    def from_message(self, message):
        return self.from_reader(message.get_root(self._schema))

    def to_message(self, dataobject, message):
        self.to_builder(dataobject, message.init_root(self._schema))


#
# Collection-type converters.
#


class _StructConverter:
    """Converter between dataclass and struct."""

    # Handle recursive dataclass reference with a global table of
    # instances.
    _INSTANCES = {}
    _INSTANCES_LOCK = threading.Lock()

    @classmethod
    def get(cls, schema, dataclass):
        key = (schema.proto.id, dataclass)
        cls._INSTANCES_LOCK.acquire()
        try:
            converter = cls._INSTANCES.get(key)
            if converter is None:
                converter = cls._INSTANCES[key] = cls()
                cls._INSTANCES_LOCK.release()
                try:
                    converter._init(schema, dataclass)
                finally:
                    cls._INSTANCES_LOCK.acquire()
        finally:
            cls._INSTANCES_LOCK.release()
        return converter

    @staticmethod
    def _compile(schema, dataclass):
        LOG.debug('compile struct converter for: %r, %r', schema, dataclass)
        # Match type names strictly to reduce the chance that
        # _NamedUnionConverter could match wrong member types.
        TYPE_ASSERT(
            schema.name == dataclass.__name__
            or schema.name == upper_to_lower_camel_case(dataclass.__name__),
            'expect __name__ == {!r}, which is derived from {!r}, '
            'but find {!r}',
            schema.name,
            schema,
            dataclass,
        )
        dataclass_fields = dataclasses.fields(dataclass)
        TYPE_ASSERT.equal(len(schema.fields), len(dataclass_fields))
        converters = []
        for sf, df in zip(_fields_by_code_order(schema), dataclass_fields):
            # Match field names strictly to reduce the chance that
            # _NamedUnionConverter could match wrong member types.
            camel_case_name = snake_to_camel_case(df.name)
            TYPE_ASSERT(
                sf.proto.name == camel_case_name,
                'expect schema field %r, which is derived from '
                'dataclass field %r, but find %r',
                camel_case_name,
                sf.proto.name,
                df.name,
            )
            if sf.proto.name in schema.union_fields:
                make = _make_struct_field_to_union_member_converter
            else:
                make = _make_field_converter
            converters.append((sf.proto.name, df.name) +
                              make(sf.type, df.type))
        return converters

    def __init__(self):
        self._dataclass = None
        self._converters = None

    def _init(self, schema, dataclass):
        self._dataclass = dataclass
        self._converters = self._compile(schema, dataclass)

    def from_reader(self, reader):
        return self._dataclass(
            **{
                df_name: getter(reader, sf_name)
                for sf_name, df_name, getter, _ in self._converters
            }
        )

    def to_builder(self, dataobject, builder):
        for sf_name, df_name, _, setter in self._converters:
            setter(builder, sf_name, getattr(dataobject, df_name))


class _TupleConverter:
    """Converter between tuple and struct."""

    @staticmethod
    def _compile(schema, element_types):
        LOG.debug('compile tuple converter for: %r, %r', schema, element_types)
        TYPE_ASSERT.equal(len(schema.fields), len(element_types))
        converters = []
        for sf, element_type in zip(
            _fields_by_code_order(schema),
            element_types,
        ):
            if sf.proto.name in schema.union_fields:
                make = _make_struct_field_to_union_member_converter
            else:
                make = _make_field_converter
            converters.append((sf.proto.name, ) + make(sf.type, element_type))
        return converters

    def __init__(self, schema, element_types):
        self._converters = self._compile(schema, element_types)

    def from_reader(self, reader):
        return tuple(
            getter(reader, sf_name) for sf_name, getter, _ in self._converters
        )

    def to_builder(self, elements, builder):
        ASSERT.equal(len(elements), len(self._converters))
        for (sf_name, _, setter), element in zip(self._converters, elements):
            setter(builder, sf_name, element)


class _ExceptionConverter:
    """Converter between Exception and struct."""

    # Only handle these simple types for now.
    _SIMPLE_TYPE_MAP = {
        _capnp.schema.Type.Which.VOID: NoneType,
        _capnp.schema.Type.Which.BOOL: bool,
        _capnp.schema.Type.Which.INT8: int,
        _capnp.schema.Type.Which.INT16: int,
        _capnp.schema.Type.Which.INT32: int,
        _capnp.schema.Type.Which.INT64: int,
        _capnp.schema.Type.Which.UINT8: int,
        _capnp.schema.Type.Which.UINT16: int,
        _capnp.schema.Type.Which.UINT32: int,
        _capnp.schema.Type.Which.UINT64: int,
        _capnp.schema.Type.Which.FLOAT32: float,
        _capnp.schema.Type.Which.FLOAT64: float,
        _capnp.schema.Type.Which.TEXT: str,
        _capnp.schema.Type.Which.DATA: bytes,
    }

    def __init__(self, schema, exc_type):
        TYPE_ASSERT(
            schema.name == exc_type.__name__
            or schema.name == upper_to_lower_camel_case(exc_type.__name__),
            'expect __name__ == {!r}, which is derived from {!r}, '
            'but find {!r}',
            schema.name,
            schema,
            exc_type,
        )
        self._converter = _TupleConverter(
            schema,
            [
                TYPE_ASSERT.getitem(self._SIMPLE_TYPE_MAP, sf.type.which)
                for sf in _fields_by_code_order(schema)
            ],
        )
        self._exc_type = exc_type

    def from_reader(self, reader):
        return self._exc_type(*self._converter.from_reader(reader))

    def to_builder(self, exc, builder):
        self._converter.to_builder(exc.args, builder)


class _ListConverter:
    """Converter between typing.List[T] and List(T)."""

    def __init__(self, schema, element_type):
        self._getter, self._setter = _make_field_converter(
            schema.element_type, element_type
        )

    def from_reader(self, reader):
        ASSERT.isinstance(reader, dynamics.DynamicListReader)
        return [self._getter(reader, i) for i in range(len(reader))]

    def to_builder(self, elements, builder):
        ASSERT.isinstance(builder, dynamics.DynamicListBuilder)
        for i, element in enumerate(elements):
            self._setter(builder, i, element)


class _NamedUnionConverter:
    """Converter between typing.Union field and a named union.

    This is half field converter (typing.Union field) and half
    collection-type converter (named union).
    """

    @staticmethod
    def _compile(schema, member_types):
        LOG.debug(
            'compile named union converter for: %r, %r', schema, member_types
        )
        member_type_set = set(member_types)
        TYPE_ASSERT.equal(len(schema.fields), len(member_type_set))
        TYPE_ASSERT.empty(schema.non_union_fields)
        converters = {}
        # TODO: This matching algorithm is non-deterministic because it
        # depends on the order of ``member_type_set`` iteration.  To
        # make things worse, ``_make_union_member_converter`` is not a
        # perfect matcher (it could match dataclass to struct type).  So
        # we might non-deterministically match dataclass to wrong struct
        # type.  How do we fix this?
        for field in schema.fields.values():
            for member_type in member_type_set:
                try:
                    result = _make_union_member_converter(
                        field.type, member_type
                    )
                except TypeError:
                    pass
                else:
                    converters[member_type] = (field.proto.name, ) + result
                    member_type_set.remove(member_type)
                    break
            else:
                TYPE_ASSERT.unreachable(
                    'no matching union member type: {!r}, {!r}, {!r}',
                    field,
                    member_types,
                    member_type_set,
                )
        return converters

    def __init__(self, schema, member_types):
        self._converters = self._compile(schema, member_types)

    def getter(self, reader, name):
        return self._getter(reader, name, reader[name])

    def union_getter(self, reader, name):
        union = reader[name]
        if union is None:
            return None
        return self._getter(reader, name, union)

    def _getter(self, reader, name, union):
        # TODO: Is there a faster way to find the selected union member?
        has_none_type = False
        for member_type, (member_name, getter, _) in self._converters.items():
            value = getter(union, member_name)
            if value is not None:
                return value
            elif issubclass(member_type, NoneType):
                has_none_type = True
        if has_none_type:
            return None
        return ASSERT.unreachable(
            'no union member is selected: {!r}, {!r}', reader, name
        )

    def setter(self, builder, name, value):
        if value is None:
            return
        member = self._converters.get(type(value))
        if member is None:
            # Find the member the slow way.
            for member_type, member in self._converters.items():
                if isinstance(value, member_type) or (
                    value is _capnp.VOID and issubclass(member_type, NoneType)
                ):
                    break
            else:
                ASSERT.unreachable(
                    'value does not match any member type: {!r}, {!r}',
                    value,
                    list(self._converters.keys()),
                )
        member_name, _, setter = member
        setter(builder.init(name), member_name, value)


#
# Field converter constructors.
#

_INT_TYPES = frozenset((
    _capnp.schema.Type.Which.INT8,
    _capnp.schema.Type.Which.INT16,
    _capnp.schema.Type.Which.INT32,
    _capnp.schema.Type.Which.INT64,
    _capnp.schema.Type.Which.UINT8,
    _capnp.schema.Type.Which.UINT16,
    _capnp.schema.Type.Which.UINT32,
    _capnp.schema.Type.Which.UINT64,
))

_FLOAT_TYPES = frozenset((
    _capnp.schema.Type.Which.FLOAT32,
    _capnp.schema.Type.Which.FLOAT64,
))

_POINTER_TYPES = frozenset((
    _capnp.schema.Type.Which.TEXT,
    _capnp.schema.Type.Which.DATA,
    _capnp.schema.Type.Which.LIST,
    _capnp.schema.Type.Which.STRUCT,
))

_DATETIME_INT_TYPES = frozenset((
    _capnp.schema.Type.Which.INT32,
    _capnp.schema.Type.Which.INT64,
    _capnp.schema.Type.Which.UINT32,
    _capnp.schema.Type.Which.UINT64,
))

_DATETIME_FLOAT_TYPE = _capnp.schema.Type.Which.FLOAT64


def _make_field_converter(sf_type, df_type):

    if typings.is_recursive_type(df_type):

        if df_type.__origin__ is list:
            TYPE_ASSERT.equal(len(df_type.__args__), 1)
            TYPE_ASSERT.true(sf_type.is_list())
            return _CollectionTypedFieldConverter.make_list_accessors(
                _ListConverter(sf_type.as_list(), df_type.__args__[0])
            )

        elif df_type.__origin__ is tuple:
            TYPE_ASSERT.true(sf_type.is_struct())
            return _CollectionTypedFieldConverter.make_accessors(
                _TupleConverter(sf_type.as_struct(), df_type.__args__)
            )

        elif typings.is_union_type(df_type):
            TYPE_ASSERT.true(sf_type.is_struct())
            converter = _NamedUnionConverter(
                sf_type.as_struct(), df_type.__args__
            )
            return converter.getter, converter.setter

        else:
            return TYPE_ASSERT.unreachable(
                'unsupported generic type: {!r}', df_type
            )

    elif is_dataclass(df_type):
        TYPE_ASSERT.true(sf_type.is_struct())
        return _CollectionTypedFieldConverter.make_accessors(
            _StructConverter.get(sf_type.as_struct(), df_type)
        )

    elif issubclass(df_type, Exception):
        TYPE_ASSERT.true(sf_type.is_struct())
        return _CollectionTypedFieldConverter.make_accessors(
            _ExceptionConverter(sf_type.as_struct(), df_type)
        )

    elif issubclass(df_type, datetime.datetime):
        if sf_type.which is _DATETIME_FLOAT_TYPE:
            return _datetime_getter, _datetime_setter_float
        else:
            TYPE_ASSERT.in_(sf_type.which, _DATETIME_INT_TYPES)
            return _datetime_getter, _datetime_setter_int

    elif issubclass(df_type, enum.Enum):
        TYPE_ASSERT.true(sf_type.is_enum())
        return functools.partial(_enum_getter, df_type), operator.setitem

    elif issubclass(df_type, NoneType):
        TYPE_ASSERT.true(sf_type.is_void())
        return _none_getter, _none_setter

    elif issubclass(df_type, _capnp.VoidType):
        TYPE_ASSERT.true(sf_type.is_void())
        return operator.getitem, operator.setitem

    elif issubclass(df_type, bool):
        TYPE_ASSERT.true(sf_type.is_bool())
        return operator.getitem, operator.setitem

    elif issubclass(df_type, int):
        TYPE_ASSERT.in_(sf_type.which, _INT_TYPES)
        return operator.getitem, operator.setitem

    elif issubclass(df_type, float):
        TYPE_ASSERT.in_(sf_type.which, _FLOAT_TYPES)
        return operator.getitem, operator.setitem

    elif issubclass(df_type, bytes):
        TYPE_ASSERT.true(sf_type.is_data())
        return _bytes_getter, _pointer_setter

    elif issubclass(df_type, str):
        TYPE_ASSERT.true(sf_type.is_text())
        return operator.getitem, _pointer_setter

    else:
        return TYPE_ASSERT.unreachable(
            'unsupported field type: {!r}, {!r}', sf_type, df_type
        )


def _make_struct_field_to_union_member_converter(sf_type, df_type):
    """Make a converter for a union member.

    * ``sf_type`` should be a member field type of an unnamed union.
    * ``df_type`` should be a typing.Union annotation (not a type
      parameter of that annotation).
    """
    if isinstance(df_type, type) and issubclass(df_type, NoneType):
        # Handle typing.Optional[NoneType], which is simply NoneType.
        return _make_union_member_converter(sf_type, df_type)
    TYPE_ASSERT.predicate(df_type, typings.is_recursive_type)
    TYPE_ASSERT.predicate(df_type, typings.is_union_type)
    type_ = typings.match_optional_type(df_type)
    if type_:
        # Handle typing.Optional[T] or typing.Union[T, NoneType].
        return _make_union_member_converter(sf_type, type_)
    else:
        # Handle typing.Union[U, V, ...].
        TYPE_ASSERT.true(sf_type.is_struct())
        converter = _NamedUnionConverter(sf_type.as_struct(), df_type.__args__)
        return converter.union_getter, converter.setter


def _make_union_member_converter(sf_type, df_type):
    """Make a converter for a union member.

    * ``sf_type`` should be a member field type of a named union.
    * ``df_type`` should be a type parameter of a typing.Union
      annotation.

    Call this on each field when you are mapping a named union to a
    typing.Union.
    """

    if typings.is_recursive_type(df_type):

        #
        # NOTE: Python typing does not supported nested union; e.g.,
        # typing.Union[typing.Optional[int], str] is equivalent to
        # typing.Union[NoneType, int, str], and so we do not match union
        # type on ``df_type`` here.
        #

        if df_type.__origin__ is list:
            TYPE_ASSERT.equal(len(df_type.__args__), 1)
            TYPE_ASSERT.true(sf_type.is_list())
            return _CollectionTypedFieldConverter.make_union_list_accessors(
                _ListConverter(sf_type.as_list(), df_type.__args__[0])
            )

        elif df_type.__origin__ is tuple:
            TYPE_ASSERT.true(sf_type.is_struct())
            return _CollectionTypedFieldConverter.make_union_accessors(
                _TupleConverter(sf_type.as_struct(), df_type.__args__)
            )

        else:
            return TYPE_ASSERT.unreachable(
                'unsupported generic type for union: {!r}', df_type
            )

    elif is_dataclass(df_type):
        TYPE_ASSERT.true(sf_type.is_struct())
        return _CollectionTypedFieldConverter.make_union_accessors(
            _StructConverter.get(sf_type.as_struct(), df_type)
        )

    elif issubclass(df_type, Exception):
        TYPE_ASSERT.true(sf_type.is_struct())
        return _CollectionTypedFieldConverter.make_union_accessors(
            _ExceptionConverter(sf_type.as_struct(), df_type)
        )

    elif issubclass(df_type, datetime.datetime):
        if sf_type.which is _DATETIME_FLOAT_TYPE:
            return _union_datetime_getter, _union_datetime_setter_float
        else:
            TYPE_ASSERT.in_(sf_type.which, _DATETIME_INT_TYPES)
            return _union_datetime_getter, _union_datetime_setter_int

    elif issubclass(df_type, enum.Enum):
        TYPE_ASSERT.true(sf_type.is_enum())
        return functools.partial(_union_enum_getter, df_type), _union_setter

    elif issubclass(df_type, NoneType):
        TYPE_ASSERT.true(sf_type.is_void())
        return _union_none_getter, _union_setter

    elif issubclass(df_type, _capnp.VoidType):
        TYPE_ASSERT.true(sf_type.is_void())
        return operator.getitem, _union_setter

    elif issubclass(df_type, bool):
        TYPE_ASSERT.true(sf_type.is_bool())
        return operator.getitem, _union_setter

    elif issubclass(df_type, int):
        TYPE_ASSERT.in_(sf_type.which, _INT_TYPES)
        return operator.getitem, _union_setter

    elif issubclass(df_type, float):
        TYPE_ASSERT.in_(sf_type.which, _FLOAT_TYPES)
        return operator.getitem, _union_setter

    elif issubclass(df_type, bytes):
        TYPE_ASSERT.true(sf_type.is_data())
        return _bytes_getter, _union_setter

    elif issubclass(df_type, str):
        TYPE_ASSERT.true(sf_type.is_text())
        return operator.getitem, _union_setter

    else:
        return TYPE_ASSERT.unreachable(
            'unsupported union member type: {!r}, {!r}', sf_type, df_type
        )


#
# Field converters.
#


class _CollectionTypedFieldConverter:
    """Collection-typed field converter.

    Note that collection types are pointer types.
    """

    @classmethod
    def make_accessors(cls, converter):
        converter = cls(converter)
        return converter.getter, converter.setter

    @classmethod
    def make_list_accessors(cls, converter):
        converter = cls(converter)
        return converter.getter, converter.list_setter

    @classmethod
    def make_union_accessors(cls, converter):
        converter = cls(converter)
        return converter.getter, converter.union_setter

    @classmethod
    def make_union_list_accessors(cls, converter):
        converter = cls(converter)
        return converter.getter, converter.union_list_setter

    def __init__(self, converter):
        self._converter = converter

    def getter(self, reader, name):
        pointer = reader[name]
        if pointer is None:
            return None
        return self._converter.from_reader(pointer)

    def setter(self, builder, name, pointer):
        if pointer is None:
            del builder[name]
        else:
            self._converter.to_builder(pointer, builder.init(name))

    def list_setter(self, builder, name, pointer):
        if pointer is None:
            del builder[name]
        else:
            self._converter.to_builder(
                pointer, builder.init(name, len(pointer))
            )

    def union_setter(self, builder, name, pointer):
        if pointer is not None:
            self._converter.to_builder(pointer, builder.init(name))

    def union_list_setter(self, builder, name, pointer):
        if pointer is not None:
            self._converter.to_builder(
                pointer, builder.init(name, len(pointer))
            )


def _bytes_getter(reader, name):
    view = reader[name]
    if view is None:
        return None
    else:
        return view.tobytes()


def _datetime_getter(reader, name):
    return datetimes.utcfromtimestamp(reader[name])


def _datetime_setter_int(builder, name, datetime_object):
    builder[name] = int(datetime_object.timestamp())


def _datetime_setter_float(builder, name, datetime_object):
    builder[name] = datetime_object.timestamp()


def _enum_getter(enum_type, reader, name):
    return enum_type(reader[name])


def _none_getter(reader, name):  # pylint: disable=useless-return
    ASSERT.is_(reader[name], _capnp.VOID)
    return None


def _none_setter(builder, name, none):
    ASSERT.is_(none, None)
    builder[name] = _capnp.VOID


def _pointer_setter(builder, name, pointer):
    if pointer is None:
        del builder[name]
    else:
        builder[name] = pointer


def _union_datetime_getter(reader, name):
    timestamp = reader[name]
    if timestamp is None:
        return None
    return datetimes.utcfromtimestamp(timestamp)


def _union_datetime_setter_int(builder, name, datetime_object):
    if datetime_object is not None:
        builder[name] = int(datetime_object.timestamp())


def _union_datetime_setter_float(builder, name, datetime_object):
    if datetime_object is not None:
        builder[name] = datetime_object.timestamp()


def _union_enum_getter(enum_type, reader, name):
    enum_value = reader[name]
    if enum_value is None:
        return None
    return enum_type(enum_value)


def _union_none_getter(reader, name):  # pylint: disable=useless-return
    ASSERT.in_(reader[name], (None, _capnp.VOID))
    return None


def _union_setter(builder, name, value):
    if value is not None:
        builder[name] = value


#
# Utility functions.
#


def is_dataclass(dataclass):
    return dataclasses.is_dataclass(dataclass) and isinstance(dataclass, type)


_SNAKE_TO_CAMEL_PATTERN = re.compile(r'_(\w)')


def snake_to_camel_case(snake_case):
    return _SNAKE_TO_CAMEL_PATTERN.sub(
        lambda match: match.group(1).upper(),
        snake_case.lower(),
    )


def upper_to_lower_camel_case(camel_case):
    return camel_case[0].lower() + camel_case[1:]


def _fields_by_code_order(schema):
    return sorted(
        schema.fields.values(), key=lambda field: field.proto.code_order
    )
