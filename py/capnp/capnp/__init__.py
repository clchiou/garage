"""Provide a Pythonic API layer on top of the native extension.

If you don't like this API layer, you may use the capnp.native module
directly, which offers a 1:1 mapping to Cap'n Proto C++ API.

This module provides three groups of functionalities:
* Load and traverse schema objects.
* Access Cap'n Proto data dynamically with reflection.
* Generate Python class from schema.
"""

__all__ = [
    'Schema',
    'SchemaLoader',

    'DynamicEnum',
    'DynamicList',
    'DynamicStruct',
    'DynamicValue',
]

from collections import OrderedDict
from pathlib import Path
import contextlib
import enum
import logging
import os

from . import native


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


#
# Load and traverse schema objects.
#


def repr_object(obj):
    """The default __repr__ implementation."""
    cls = obj.__class__
    return ('<%s.%s 0x%x %s>' %
            (cls.__module__, cls.__qualname__, id(obj), obj))


class SchemaLoader:
    """Load Cap'n Proto schema.

    The loaded schemas are stored in `schemas`.  Also, top-level
    declarations are referenced from `declarations` (this is useful when
    you want to generate Python classes from the schema file).
    """

    def __init__(self):
        self._loader = None
        self.files = OrderedDict()
        self.schemas = OrderedDict()
        self.declarations = []  # Top-level declarations.
        self._node_ids = set()

    def __enter__(self):
        assert self._loader is None
        self._loader = native.SchemaLoader()
        return self

    def __exit__(self, *_):
        self._loader, loader = None, self._loader
        loader._reset()

    def load(self, schema_path):
        """Load schema from a file."""
        if not isinstance(schema_path, Path):
            schema_path = Path(schema_path)
        self.load_from(schema_path.read_bytes())

    def load_from(self, blob):
        """Load schema from a binary blob in memory."""
        assert self._loader is not None
        with _make_bytes_reader(blob) as reader:
            codegen_request = reader.getRoot()
            for node in codegen_request.getNodes():
                self._loader.load(node)
            for requested_file in codegen_request.getRequestedFiles():
                self._load(requested_file.getId(), 0)

    def _load(self, node_id, depth):
        """Recursively traverse and load nodes."""

        if node_id in self._node_ids:
            return

        self._node_ids.add(node_id)

        schema = self._loader.get(node_id)
        node = schema.getProto()

        if node.isAnnotation():
            pass  # We don't track annotation definitions, yet.

        elif node.isFile():
            file_node = FileNode(node)
            assert node_id == file_node.id
            self.files[node_id] = file_node

        else:
            schema = Schema(self.schemas, schema)
            assert node_id == schema.id
            self.schemas[node_id] = schema
            if depth == 1:  # Collect top-level declarations.
                self.declarations.append(schema)

        for nested_node in node.getNestedNodes():
            self._load(nested_node.getId(), depth + 1)
        for annotation in node.getAnnotations():
            self._load(annotation.getId(), depth + 1)


class Node:
    """Represent low-level schema.capnp Node object.

    You usually don't need to access this, but other classes that wrap
    this and expose higher-level interface.
    """

    class Kind(enum.Enum):

        @classmethod
        def from_node(cls, node):
            for kind in cls:
                if kind.izzer(node):
                    return kind
            raise AssertionError(
                'undefined node kind: %s' % node.getDisplayName())

        FILE = (native.schema.Node.isFile,)
        STRUCT = (native.schema.Node.isStruct,)
        ENUM = (native.schema.Node.isEnum,)
        INTERFACE = (native.schema.Node.isInterface,)
        CONST = (native.schema.Node.isConst,)
        ANNOTATION = (native.schema.Node.isAnnotation,)

        def __init__(self, izzer):
            self.izzer = izzer

    def __init__(self, node):
        assert not node.getIsGeneric(), 'do not support generics yet'
        self._node = node
        self.id = self._node.getId()
        self.kind = Node.Kind.from_node(self._node)
        self.name = self._node.getDisplayName()
        self.annotations = tuple(map(Annotation, self._node.getAnnotations()))

    def __str__(self):
        return self.name

    __repr__ = repr_object


class FileNode(Node):

    def __init__(self, node):
        assert node.isFile()
        super().__init__(node)
        self.node_ids = tuple(nn.getId() for nn in self._node.getNestedNodes())


class Schema:
    """Represent schema for various kind of entities.

    Schema has a two generic properties: `id` and `kind`.
    * `id` is unique among all schemas and is the key of the
      `schema_table` of SchemaLoader.
    * `kind` describes the specific details of this Schema object.
    """

    class Kind(enum.Enum):

        @classmethod
        def from_node(cls, node):
            if node.kind is Node.Kind.STRUCT:
                return cls.STRUCT
            elif node.kind is Node.Kind.ENUM:
                return cls.ENUM
            elif node.kind is Node.Kind.INTERFACE:
                return cls.INTERFACE
            elif node.kind is Node.Kind.CONST:
                type_kind = Type.Kind.from_type(node.asConst().getType())
                return type_kind.schema_kind
            else:
                raise AssertionError('unrecognizable schema type: %s' % node)

        PRIMITIVE = enum.auto()
        BLOB = enum.auto()
        ENUM = enum.auto()
        STRUCT = enum.auto()
        UNION = enum.auto()
        INTERFACE = enum.auto()
        LIST = enum.auto()

        OTHER = enum.auto()

    def __init__(self, schema_table, schema):

        if isinstance(schema, native.ListSchema):
            self._proto = None
            self.id = _get_list_type_id(schema)
            self.kind = Schema.Kind.LIST
        else:
            self._proto = Node(schema.getProto())
            self.id = self._proto.id
            self.kind = Schema.Kind.from_node(self._proto)

        if self._proto and self._proto.kind is Node.Kind.CONST:
            LOG.debug('construct const schema: %s', self._proto)
            self._schema = schema.asConst()
            self.type = Type(schema_table, self._schema.getType())
            self.value = Value(self._schema.asDynamicValue())

        elif self.kind is Schema.Kind.ENUM:
            LOG.debug('construct enum schema: %s', self._proto)
            self._schema = schema.asEnum()
            self.enumerants = tuple(map(
                Enumerant, self._schema.getEnumerants()))
            self._dict = OrderedDict(
                (enumerant.name, enumerant)
                for enumerant in self.enumerants
            )

        elif self.kind is Schema.Kind.INTERFACE:
            LOG.debug('construct interface schema: %s', self._proto)
            self._schema = schema.asInterface()
            # TODO: Load interface schema data.

        elif self.kind is Schema.Kind.LIST:
            assert isinstance(schema, native.ListSchema)
            self._schema = schema
            self.element_type = Type(
                schema_table, self._schema.getElementType())
            LOG.debug('construct schema for list of %s', self.element_type)

        elif self.kind is Schema.Kind.STRUCT:
            LOG.debug('construct struct schema: %s', self._proto)
            self._schema = schema.asStruct()
            self.fields = self._get_fields(schema_table)
            self.union_fields = self._collect_fields(
                self._schema.getUnionFields())
            self.non_union_fields = self._collect_fields(
                self._schema.getNonUnionFields())
            self._dict = OrderedDict(
                (field.name, field)
                for field in self.fields
            )

        else:
            raise AssertionError('unsupported kind of schema: %s' % self.kind)

    def __str__(self):
        if self.kind is Schema.Kind.LIST:
            return '%s<%s>' % (self.kind.name, self.element_type)
        else:
            return str(self._proto)

    __repr__ = repr_object

    def __contains__(self, name):
        assert self.kind in (Schema.Kind.ENUM, Schema.Kind.STRUCT)
        return name in self._dict

    def __iter__(self):
        assert self.kind in (Schema.Kind.ENUM, Schema.Kind.STRUCT)
        yield from self._dict

    def get(self, name, default=None):
        assert self.kind in (Schema.Kind.ENUM, Schema.Kind.STRUCT)
        return self._dict.get(name, default)

    def __getitem__(self, name):
        assert self.kind in (Schema.Kind.ENUM, Schema.Kind.STRUCT)
        return self._dict[name]

    def _get_fields(self, schema_table):
        fields = tuple(
            Field(schema_table, field) for field in self._schema.getFields())
        assert all(i == field.index for i, field in enumerate(fields))
        return fields

    def _collect_fields(self, field_subset):
        return tuple(self.fields[field.getIndex()] for field in field_subset)


class Enumerant:

    def __init__(self, enumerant):
        self._enumerant = enumerant
        self._proto = self._enumerant.getProto()
        self.name = self._proto.getName()
        self.oridinal = self._enumerant.getOrdinal()
        self.index = self._enumerant.getIndex()
        self.annotations = tuple(map(Annotation, self._proto.getAnnotations()))


class Field:

    def __init__(self, schema_table, field):
        self._field = field
        self._proto = self._field.getProto()
        self.name = self._proto.getName()
        self.index = self._field.getIndex()
        self.type = Type(schema_table, self._field.getType())
        self.annotations = tuple(map(Annotation, self._proto.getAnnotations()))

    def __str__(self):
        return self.name

    __repr__ = repr_object


class Annotation:

    class Kind(enum.Enum):
        """Enumeration of some well-known / built-in annotations."""

        @classmethod
        def from_id(cls, node_id):
            for kind in cls:
                if kind.value == node_id:
                    return kind
            return cls.UNIDENTIFIED

        UNIDENTIFIED = -1

        # Annotation node id from capnp/c++.capnp.
        CXX_NAMESPACE = 0xb9c6f99ebf805f2c
        CXX_NAME = 0xf264a779fef191ce

    def __init__(self, annotation):
        self._annotation = annotation
        self.id = self._annotation.getId()
        self.value = Value(self._annotation.getValue())
        self.kind = Annotation.Kind.from_id(self.id)

    def __str__(self):
        return '<%d = %s: %s>' % (self.id, self.kind, self.value)

    __repr__ = repr_object


class Type:

    class Kind(enum.Enum):

        @classmethod
        def from_type(cls, type_):
            for kind in cls:
                if kind.izzer(type_):
                    return kind
            raise AssertionError('undefined type kind: %s' % type_)

        VOID = (native.Type.isVoid, Schema.Kind.OTHER)
        BOOL = (native.Type.isBool, Schema.Kind.PRIMITIVE)
        INT8 = (native.Type.isInt8, Schema.Kind.PRIMITIVE)
        INT16 = (native.Type.isInt16, Schema.Kind.PRIMITIVE)
        INT32 = (native.Type.isInt32, Schema.Kind.PRIMITIVE)
        INT64 = (native.Type.isInt64, Schema.Kind.PRIMITIVE)
        UINT8 = (native.Type.isUInt8, Schema.Kind.PRIMITIVE)
        UINT16 = (native.Type.isUInt16, Schema.Kind.PRIMITIVE)
        UINT32 = (native.Type.isUInt32, Schema.Kind.PRIMITIVE)
        UINT64 = (native.Type.isUInt64, Schema.Kind.PRIMITIVE)
        FLOAT32 = (native.Type.isFloat32, Schema.Kind.PRIMITIVE)
        FLOAT64 = (native.Type.isFloat64, Schema.Kind.PRIMITIVE)
        TEXT = (native.Type.isText, Schema.Kind.BLOB)
        DATA = (native.Type.isData, Schema.Kind.BLOB)
        LIST = (native.Type.isList, Schema.Kind.LIST)
        ENUM = (native.Type.isEnum, Schema.Kind.ENUM)
        STRUCT = (native.Type.isStruct, Schema.Kind.STRUCT)
        INTERFACE = (native.Type.isInterface, Schema.Kind.INTERFACE)
        ANY_POINTER = (native.Type.isAnyPointer, Schema.Kind.OTHER)

        def __init__(self, izzer, schema_kind):
            self.izzer = izzer
            self.schema_kind = schema_kind

    @staticmethod
    def _make_schema(schema_table, schema):
        if isinstance(schema, native.ListSchema):
            node_id = _get_list_type_id(schema)
        else:
            node_id = schema.getProto().getId()
        if node_id in schema_table:
            return schema_table[node_id]
        else:
            schema = Schema(schema_table, schema)
            assert node_id == schema.id
            schema_table[node_id] = schema
            return schema

    def __init__(self, schema_table, type_):
        self._type = type_
        self.kind = Type.Kind.from_type(self._type)

        if self.kind is Type.Kind.ENUM:
            self.schema = self._make_schema(schema_table, self._type.asEnum())
        elif self.kind is Type.Kind.INTERFACE:
            self.schema = self._make_schema(
                schema_table, self._type.asInterface())
        elif self.kind is Type.Kind.LIST:
            self.schema = self._make_schema(schema_table, self._type.asList())
        elif self.kind is Type.Kind.STRUCT:
            self.schema = self._make_schema(
                schema_table, self._type.asStruct())
        else:
            self.schema = None

    def __str__(self):
        return self.kind.name

    __repr__ = repr_object


class Value:
    """Represent Value struct of schema.capnp.

    Don't confuse this with DynamicValue.
    """

    # type_kind, python_type, izzer, hazzer, getter
    _TYPE_TABLE = (

        (
            Type.Kind.VOID, type(None),
            native.schema.Value.isVoid, None, lambda _: None,
        ),

        (
            Type.Kind.BOOL, bool,
            native.schema.Value.isBool, None, native.schema.Value.getBool,
        ),
        (
            Type.Kind.INT8, int,
            native.schema.Value.isInt8, None, native.schema.Value.getInt8,
        ),
        (
            Type.Kind.INT16, int,
            native.schema.Value.isInt16, None, native.schema.Value.getInt16,
        ),
        (
            Type.Kind.INT32, int,
            native.schema.Value.isInt32, None, native.schema.Value.getInt32,
        ),
        (
            Type.Kind.INT64, int,
            native.schema.Value.isInt64, None, native.schema.Value.getInt64,
        ),
        (
            Type.Kind.UINT8, int,
            native.schema.Value.isUint8, None, native.schema.Value.getUint8,
        ),
        (
            Type.Kind.UINT16, int,
            native.schema.Value.isUint16, None, native.schema.Value.getUint16,
        ),
        (
            Type.Kind.UINT32, int,
            native.schema.Value.isUint32, None, native.schema.Value.getUint32,
        ),
        (
            Type.Kind.UINT64, int,
            native.schema.Value.isUint64, None, native.schema.Value.getUint64,
        ),
        (
            Type.Kind.FLOAT32,
            float,
            native.schema.Value.isFloat32,
            None,
            native.schema.Value.getFloat32,
        ),
        (
            Type.Kind.FLOAT64,
            float,
            native.schema.Value.isFloat64,
            None,
            native.schema.Value.getFloat64,
        ),

        (
            Type.Kind.TEXT,
            str,
            native.schema.Value.isText,
            native.schema.Value.hasText,
            native.schema.Value.getText,
        ),
        (
            Type.Kind.DATA,
            bytes,
            native.schema.Value.isData,
            native.schema.Value.hasData,
            native.schema.Value.getData,
        ),

        (
            Type.Kind.LIST,
            tuple,
            native.schema.Value.isList,
            native.schema.Value.hasList,
            native.schema.Value.getList,
        ),

        (
            Type.Kind.ENUM,
            int,
            native.schema.Value.isEnum, None, native.schema.Value.getEnum,
        ),

        (
            Type.Kind.STRUCT,
            object,
            native.schema.Value.isStruct,
            native.schema.Value.hasStruct,
            native.schema.Value.getStruct,
        ),

        (
            Type.Kind.INTERFACE, type(None),
            native.schema.Value.isInterface, None, lambda _: None,
        ),

        (
            Type.Kind.ANY_POINTER,
            object,
            native.schema.Value.isAnyPointer,
            native.schema.Value.hasAnyPointer,
            native.schema.Value.getAnyPointer,
        ),
    )

    def __init__(self, value):

        type_kind = python_type = izzer = hazzer = getter = None
        for type_kind, python_type, izzer, hazzer, getter in self._TYPE_TABLE:
            if izzer(value):
                break
        else:
            raise AssertionError('unsupported value: %s' % value)

        self.type_kind = type_kind
        self._value = value
        self._has_value = not hazzer or hazzer(self._value)
        if self._has_value:
            python_value = getter(self._value)
            if type_kind is Type.Kind.LIST:
                raise NotImplementedError  # TODO: Handle AnyPointer.
            elif type_kind is Type.Kind.STRUCT:
                raise NotImplementedError  # TODO: Handle AnyPointer.
            elif type_kind is Type.Kind.ANY_POINTER:
                raise NotImplementedError  # TODO: Handle AnyPointer.
            else:
                self._python_value = python_value
            assert isinstance(self._python_value, python_type)
        else:
            self._python_value = None

    def get(self, default=None):
        return self._python_value if self._has_value else default

    def __str__(self):
        return '<%s: %s>' % (self.type_kind.name, self.get())

    __repr__ = repr_object


def _get_list_type_id(schema):
    """Generate an unique id for list schema.

    We cannot call schema.getProto().getId() to generate an unique id
    because ListSchema is different - it is not associated with a Node.
    """
    assert isinstance(schema, native.ListSchema)
    type_ = schema.getElementType()
    level = 0
    while type_.isList():
        type_ = type_.asList().getElementType()
        level += 1
    return (level, type_.hashCode())


#
# Access Cap'n Proto data dynamically with reflection.
#


@contextlib.contextmanager
def _make_bytes_reader(blob):
    reader = native.FlatArrayMessageReader(blob)
    try:
        yield reader
    finally:
        reader._reset()


@contextlib.contextmanager
def _make_packed_bytes_reader(blob):
    stream = native.ArrayInputStream(blob)
    try:
        reader = native.PackedMessageReader(stream)
        try:
            yield reader
        finally:
            reader._reset()
    finally:
        stream._reset()


@contextlib.contextmanager
def _make_file_reader(reader_class, path):
    fd = os.open(path, os.O_RDONLY)
    try:
        reader = reader_class(fd)
        try:
            yield reader
        finally:
            reader._reset()
    finally:
        os.close(fd)


class MessageReader:

    @classmethod
    def from_bytes(cls, blob):
        return cls(lambda: _make_bytes_reader(blob))

    @classmethod
    def from_packed_bytes(cls, blob):
        return cls(lambda: _make_packed_bytes_reader(blob))

    @classmethod
    def from_file(cls, path):
        return cls(
            lambda: _make_file_reader(native.StreamFdMessageReader, path))

    @classmethod
    def from_packed_file(cls, path):
        return cls(
            lambda: _make_file_reader(native.PackedFdMessageReader, path))

    def __init__(self, make_reader):
        self._make_reader = make_reader
        self._context = None
        self._reader = None

    def __enter__(self):
        assert self._make_reader is not None
        assert self._reader is None
        self._context = self._make_reader()
        self._make_reader = None  # _make_reader is one-time use only.
        self._reader = self._context.__enter__()
        return self

    def __exit__(self, *args):
        self._reader = None
        self._context, context = None, self._context
        return context.__exit__(*args)

    @property
    def canonical(self):
        assert self._reader is not None
        return self._reader.isCanonical()

    def get_root(self, schema):
        assert self._reader is not None
        assert schema.kind is Schema.Kind.STRUCT
        return DynamicStruct(schema, self._reader.getRoot(schema._schema))


class DynamicEnum:

    def __init__(self, schema, enum_):
        assert schema.kind is Schema.Kind.ENUM
        assert schema.id == enum_.getSchema().getProto().getId()
        self.schema = schema
        self._enum = enum_

        enumerant = self._enum.getEnumerant()
        if enumerant is None:
            self.enumerant = None
        else:
            self.enumerant = self.schema[enumerant.getProto().getName()]

    def get(self):
        return self._enum.getRaw()


class DynamicList:

    def __init__(self, schema, list_):
        assert schema.kind is Schema.Kind.LIST
        assert schema.id == _get_list_type_id(list_.getSchema())
        self.schema = schema
        self._list = list_
        self._values = tuple(
            DynamicValue(self.schema.element_type, self._list[i])
            for i in range(len(self._list))
        )

    def __len__(self):
        return len(self._list)

    def __iter__(self):
        for i in range(len(self._list)):
            yield DynamicValue(self.schema.element_type, self._list[i])

    def __getitem__(self, index):
        assert isinstance(index, int)
        if not 0 <= index < len(self._list):
            raise IndexError('not 0 <= %d < %d' % (index, len(self._list)))
        return DynamicValue(self.schema.element_type, self._list[index])

    def __str__(self):
        return str(self._values)

    __repr__ = repr_object


class DynamicStruct:

    def __init__(self, schema, struct):
        assert schema.kind is Schema.Kind.STRUCT
        assert schema.id == struct.getSchema().getProto().getId()
        self.schema = schema
        self._struct = struct

    @property
    def total_size(self):
        return self._struct.totalSize()

    def __contains__(self, name):
        return name in self.schema

    def __iter__(self):
        yield from self.schema

    def __getitem__(self, name):
        return self._get(name, None, KeyError)

    def get(self, name, default=None):
        return self._get(name, default, None)

    def _get(self, name, default, raises):
        field = self.schema[name]
        if not self._struct.has(field._field):
            if raises:
                raise raises(name)
            else:
                return default
        return DynamicValue(field.type, self._struct.get(field._field))

    def as_dict(self):
        return OrderedDict((name, self[name]) for name in self.schema)


class DynamicValue:

    # type_kinds, python_type, converter
    _TYPE_TABLE = (
        (
            frozenset((Type.Kind.VOID,)),
            type(None),
            lambda _: None,
        ),
        (
            frozenset((Type.Kind.BOOL,)),
            bool,
            native.DynamicValue.Reader.asBool,
        ),
        (
            frozenset((
                Type.Kind.INT8,
                Type.Kind.INT16,
                Type.Kind.INT32,
                Type.Kind.INT64,
            )),
            int,
            native.DynamicValue.Reader.asInt,
        ),
        (
            frozenset((
                Type.Kind.UINT8,
                Type.Kind.UINT16,
                Type.Kind.UINT32,
                Type.Kind.UINT64,
            )),
            int,
            native.DynamicValue.Reader.asUInt,
        ),
        (
            frozenset((Type.Kind.FLOAT32, Type.Kind.FLOAT64)),
            float,
            native.DynamicValue.Reader.asFloat,
        ),
        (
            frozenset((Type.Kind.TEXT,)),
            str,
            native.DynamicValue.Reader.asText,
        ),
        (
            frozenset((Type.Kind.DATA,)),
            bytes,
            native.DynamicValue.Reader.asData,
        ),
        (
            frozenset((Type.Kind.LIST,)),
            DynamicList,
            native.DynamicValue.Reader.asList,
        ),
        (
            frozenset((Type.Kind.ENUM,)),
            DynamicEnum,
            native.DynamicValue.Reader.asEnum,
        ),
        (
            frozenset((Type.Kind.STRUCT,)),
            DynamicStruct,
            native.DynamicValue.Reader.asStruct,
        ),
    )

    _DYNAMIC_TYPES = {
        Type.Kind.LIST: DynamicList,
        Type.Kind.ENUM: DynamicEnum,
        Type.Kind.STRUCT: DynamicStruct,
    }

    def __init__(self, type_, value):

        self.type = type_
        self._value = value

        type_kinds = python_type = converter = None
        for type_kinds, python_type, converter in self._TYPE_TABLE:
            if self.type.kind in type_kinds:
                break
        else:
            raise AssertionError('unsupported type: %s' % self.type)

        self.python_type = python_type
        self._converter = converter
        self._python_value = None

        self._dynamic_type = self._DYNAMIC_TYPES.get(self.type.kind)

    def get(self):
        if self._python_value is None:
            python_value = self._converter(self._value)
            if self._dynamic_type:
                assert self.type.schema is not None
                python_value = self._dynamic_type(
                    self.type.schema,
                    python_value,
                )
            assert isinstance(python_value, self.python_type)
            self._python_value = python_value
        return self._python_value
