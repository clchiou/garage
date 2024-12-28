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

Thirdly, typing.Union annotation is not supported for these reasons:

* The converter has to build a mapping from typing.Union member types to
  union members.  But the matching process is ambiguous; for example,
  typing.Tuple[int] can be matched to any compatible struct-typed union
  member.

* When setting value to a typing.Union field, the converter has to match
  value type to an union member.  But the matching process does not
  produce an unique result; for example, an empty list can be matched to
  any list-typed union member.

Given these ambiguity, plus the complexity of implementing the matching
process, we decided that we do not support typing.Union in the first
version of converter.

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
--------------  -----------------------------------

* When mapping a struct to a typing.Tuple, we sort struct fields by code
  order, which is more semantically relevant than ordinal number.
"""

# TODO(clchiou): Support generic.

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

from g1.bases import assertions
from g1.bases import cases
from g1.bases import datetimes
from g1.bases import typings
from g1.bases.assertions import ASSERT

from . import _capnp
# pylint: disable=c-extension-no-member
from . import dynamics
from . import schemas

LOG = logging.getLogger(__name__)

TYPE_ASSERT = assertions.Assertions(lambda message, *_: TypeError(message))

NoneType = type(None)


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
        if (
            schema.name != dataclass.__name__
            and schema.name != cases.upper_to_lower_camel(dataclass.__name__)
        ):
            LOG.warning(
                'expect dataclass.__name__ == %r, not %r',
                schema.name,
                dataclass.__name__,
            )
        dataclass_fields = dataclasses.fields(dataclass)
        TYPE_ASSERT.equal(len(schema.fields), len(dataclass_fields))
        converters = []
        for df in dataclass_fields:
            sf = TYPE_ASSERT.getitem(
                schema.fields, cases.lower_snake_to_lower_camel(df.name)
            )
            if sf.proto.name in schema.union_fields:
                make = _make_optional_field_converter
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
                make = _make_optional_field_converter
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

    # Handle these simple types if the Exception type is not annotated.
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
        if (
            schema.name != exc_type.__name__
            and schema.name != cases.upper_to_lower_camel(exc_type.__name__)
        ):
            LOG.warning(
                'expect exc_type.__name__ == %r, not %r',
                schema.name,
                exc_type.__name__,
            )
        args_annotation = (
            exc_type.__dict__.get('__annotations__', {}).get('args')
        )
        if args_annotation is None:
            element_types = [
                TYPE_ASSERT.getitem(self._SIMPLE_TYPE_MAP, sf.type.which)
                for sf in _fields_by_code_order(schema)
            ]
        else:
            TYPE_ASSERT(
                typings.is_recursive_type(args_annotation)
                and args_annotation.__origin__ is tuple,
                'expect typing.Tuple, not {!r}',
                args_annotation,
            )
            element_types = args_annotation.__args__
        self._converter = _TupleConverter(schema, element_types)
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
            getter, setter = _CollectionTypedFieldConverter.make_list_accessors(
                _ListConverter(sf_type.as_list(), df_type.__args__[0])
            )

        elif df_type.__origin__ is tuple:
            TYPE_ASSERT.true(sf_type.is_struct())
            getter, setter = _CollectionTypedFieldConverter.make_accessors(
                _TupleConverter(sf_type.as_struct(), df_type.__args__)
            )

        else:
            TYPE_ASSERT.unreachable(
                'unsupported generic type: {!r}', df_type
            )

    elif is_dataclass(df_type):
        TYPE_ASSERT.true(sf_type.is_struct())
        getter, setter = _CollectionTypedFieldConverter.make_accessors(
            _StructConverter.get(sf_type.as_struct(), df_type)
        )

    elif issubclass(df_type, Exception):
        TYPE_ASSERT.true(sf_type.is_struct())
        getter, setter = _CollectionTypedFieldConverter.make_accessors(
            _ExceptionConverter(sf_type.as_struct(), df_type)
        )

    elif issubclass(df_type, datetime.datetime):
        if sf_type.which is _DATETIME_FLOAT_TYPE:
            getter, setter = _datetime_getter, _datetime_setter_float
        else:
            TYPE_ASSERT.in_(sf_type.which, _DATETIME_INT_TYPES)
            getter, setter = _datetime_getter, _datetime_setter_int

    elif issubclass(df_type, enum.Enum):
        TYPE_ASSERT.true(sf_type.is_enum())
        getter, setter = functools.partial(_enum_getter, df_type), operator.setitem

    elif issubclass(df_type, NoneType):
        TYPE_ASSERT.true(sf_type.is_void())
        getter, setter = _none_getter, _none_setter

    elif issubclass(df_type, _capnp.VoidType):
        TYPE_ASSERT.true(sf_type.is_void())
        getter, setter = operator.getitem, operator.setitem

    elif issubclass(df_type, bool):
        TYPE_ASSERT.true(sf_type.is_bool())
        getter, setter = operator.getitem, operator.setitem

    elif issubclass(df_type, int):
        TYPE_ASSERT.in_(sf_type.which, _INT_TYPES)
        if df_type is int:
            getter = operator.getitem
        else:
            getter = functools.partial(_int_subtype_getter, df_type)
        setter = operator.setitem

    elif issubclass(df_type, float):
        TYPE_ASSERT.in_(sf_type.which, _FLOAT_TYPES)
        getter, setter = operator.getitem, operator.setitem

    elif issubclass(df_type, bytes):
        TYPE_ASSERT.true(sf_type.is_data())
        getter, setter = _bytes_getter, _pointer_setter

    elif issubclass(df_type, str):
        TYPE_ASSERT.true(sf_type.is_text())
        getter, setter = operator.getitem, _pointer_setter

    else:
        TYPE_ASSERT.unreachable(
            'unsupported field type: {!r}, {!r}', sf_type, df_type
        )

    return getter, setter


def _make_optional_field_converter(sf_type, df_type):
    """Make a converter for a union member.

    * ``sf_type`` should be type of a member field of a union.
    * ``df_type`` should be a typing.Optional annotation.
    """
    if typings.type_is_subclass(df_type, NoneType):
        # Handle typing.Optional[NoneType], which is simply NoneType.
        return _make_union_member_converter(sf_type, df_type)
    else:
        return _make_union_member_converter(
            sf_type,
            TYPE_ASSERT(
                typings.is_recursive_type(df_type)
                and typings.is_union_type(df_type)
                and typings.match_optional_type(df_type),
                'expect typing.Optional, not {!r}',
                df_type,
            ),
        )


def _make_union_member_converter(sf_type, df_type):

    if typings.is_recursive_type(df_type):

        if df_type.__origin__ is list:
            TYPE_ASSERT.equal(len(df_type.__args__), 1)
            TYPE_ASSERT.true(sf_type.is_list())
            getter, setter = _CollectionTypedFieldConverter.make_union_list_accessors(
                _ListConverter(sf_type.as_list(), df_type.__args__[0])
            )

        elif df_type.__origin__ is tuple:
            TYPE_ASSERT.true(sf_type.is_struct())
            getter, setter = _CollectionTypedFieldConverter.make_union_accessors(
                _TupleConverter(sf_type.as_struct(), df_type.__args__)
            )

        else:
            TYPE_ASSERT.unreachable(
                'unsupported generic type for union: {!r}', df_type
            )

    elif is_dataclass(df_type):
        TYPE_ASSERT.true(sf_type.is_struct())
        getter, setter = _CollectionTypedFieldConverter.make_union_accessors(
            _StructConverter.get(sf_type.as_struct(), df_type)
        )

    elif issubclass(df_type, Exception):
        TYPE_ASSERT.true(sf_type.is_struct())
        getter, setter = _CollectionTypedFieldConverter.make_union_accessors(
            _ExceptionConverter(sf_type.as_struct(), df_type)
        )

    elif issubclass(df_type, datetime.datetime):
        if sf_type.which is _DATETIME_FLOAT_TYPE:
            getter, setter = _union_datetime_getter, _union_datetime_setter_float
        else:
            TYPE_ASSERT.in_(sf_type.which, _DATETIME_INT_TYPES)
            getter, setter = _union_datetime_getter, _union_datetime_setter_int

    elif issubclass(df_type, enum.Enum):
        TYPE_ASSERT.true(sf_type.is_enum())
        getter, setter = functools.partial(_union_enum_getter, df_type), _union_setter

    elif issubclass(df_type, NoneType):
        TYPE_ASSERT.true(sf_type.is_void())
        getter, setter = _union_none_getter, _union_setter

    elif issubclass(df_type, _capnp.VoidType):
        TYPE_ASSERT.true(sf_type.is_void())
        getter, setter = operator.getitem, _union_setter

    elif issubclass(df_type, bool):
        TYPE_ASSERT.true(sf_type.is_bool())
        getter, setter = operator.getitem, _union_setter

    elif issubclass(df_type, int):
        TYPE_ASSERT.in_(sf_type.which, _INT_TYPES)
        if df_type is int:
            getter = operator.getitem
        else:
            getter = functools.partial(_union_int_subtype_getter, df_type)
        setter = _union_setter

    elif issubclass(df_type, float):
        TYPE_ASSERT.in_(sf_type.which, _FLOAT_TYPES)
        getter, setter = operator.getitem, _union_setter

    elif issubclass(df_type, bytes):
        TYPE_ASSERT.true(sf_type.is_data())
        getter, setter = _bytes_getter, _union_setter

    elif issubclass(df_type, str):
        TYPE_ASSERT.true(sf_type.is_text())
        getter, setter = operator.getitem, _union_setter

    else:
        TYPE_ASSERT.unreachable(
            'unsupported union member type: {!r}, {!r}', sf_type, df_type
        )

    return getter, setter


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
    return _to_enum_member(enum_type, reader[name])


def _int_subtype_getter(int_subtype, reader, name):
    return int_subtype(reader[name])


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
    return _to_enum_member(enum_type, enum_value)


def _union_int_subtype_getter(int_subtype, reader, name):
    int_value = reader[name]
    if int_value is None:
        return None
    return int_subtype(int_value)


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


def _fields_by_code_order(schema):
    return sorted(
        schema.fields.values(), key=lambda field: field.proto.code_order
    )


def _to_enum_member(enum_type, enum_value):
    try:
        return enum_type(enum_value)
    except ValueError:
        return enum_value
