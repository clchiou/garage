"""Provide a Pythonic API layer on top of the native extension.

If you don't like this API layer, you may use the capnp.native module
directly, which offers a 1:1 mapping to Cap'n Proto C++ API.
"""

__all__ = [
    'Schema',
    'SchemaLoader',
]

from collections import OrderedDict
from pathlib import Path
import enum
import logging

from . import native


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


def repr_object(obj):
    cls = obj.__class__
    return ('<%s.%s at 0x%x: %s>' %
            (cls.__module__, cls.__qualname__, id(obj), obj))


class SchemaLoader:

    def __init__(self):
        self._loader = None
        self.schemas = OrderedDict()
        self.declarations = []  # Top-level declarations.

    def __enter__(self):
        assert self._loader is None
        self._loader = native.SchemaLoader()
        return self

    def __exit__(self, *_):
        self._loader, loader = None, self._loader
        loader._reset()

    def load(self, schema_path):
        if not isinstance(schema_path, Path):
            schema_path = Path(schema_path)
        self.load_from(schema_path.read_bytes())

    def load_from(self, blob):
        assert self._loader is not None
        reader = native.FlatArrayMessageReader(blob)
        try:
            codegen_request = reader.getRoot()
            for node in codegen_request.getNodes():
                self._loader.load(node)
            for requested_file in codegen_request.getRequestedFiles():
                self._load_schema(requested_file.getId(), 0)
        finally:
            reader._reset()

    def _load_schema(self, node_id, depth):
        if node_id in self.schemas:
            return
        schema = Schema(self.schemas, self._loader.get(node_id))
        assert node_id == schema.id
        self.schemas[node_id] = schema
        if depth == 1:  # Collect top-level declarations.
            self.declarations.append(schema)
        LOG.debug('load schema: id=%d, schema=%r', node_id, schema)
        for nested_node in schema._proto._node.getNestedNodes():
            self._load_schema(nested_node.getId(), depth + 1)


class Schema:

    class Kind(enum.Enum):

        @classmethod
        def from_node(cls, node):
            if node.kind is Schema.Node.Kind.FILE:
                return cls.OTHER  # What kind should we return?
            elif node.kind is Schema.Node.Kind.STRUCT:
                return cls.STRUCT
            elif node.kind is Schema.Node.Kind.ENUM:
                return cls.ENUM
            elif node.kind is Schema.Node.Kind.INTERFACE:
                return cls.INTERFACE
            elif node.kind is Schema.Node.Kind.CONST:
                type_kind = Type.Kind.from_type(node.asConst().getType())
                return type_kind.schema_kind
            elif node.kind is Schema.Node.Kind.ANNOTATION:
                return cls.OTHER  # What kind should we return?
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

    class Node:

        class Kind(enum.Enum):

            @classmethod
            def from_node(cls, node):
                for kind in cls:
                    if kind.predicate(node):
                        return kind
                raise AssertionError(
                    'undefined node kind: %s' % node.getDisplayName())

            FILE = (native.schema.Node.isFile,)
            STRUCT = (native.schema.Node.isStruct,)
            ENUM = (native.schema.Node.isEnum,)
            INTERFACE = (native.schema.Node.isInterface,)
            CONST = (native.schema.Node.isConst,)
            ANNOTATION = (native.schema.Node.isAnnotation,)

            def __init__(self, predicate):
                self.predicate = predicate

        def __init__(self, node):
            self._node = node
            self.id = self._node.getId()
            self.kind = Schema.Node.Kind.from_node(self._node)

        def __str__(self):
            return self._node.getDisplayName()

        __repr__ = repr_object

    def __init__(self, schemas, schema):

        if isinstance(schema, native.ListSchema):
            self._proto = None
            self.id = _get_list_type_id(schema)
            self.kind = Schema.Kind.LIST
        else:
            self._proto = Schema.Node(schema.getProto())
            self.id = self._proto.id
            self.kind = Schema.Kind.from_node(self._proto)

        if self._proto and self._proto.kind is Schema.Node.Kind.CONST:
            LOG.debug('construct const schema: %s', self._proto)
            self._schema = schema.asConst()
            self.type = Type(schemas, self._schema.getType())
            self.value = Value(self._schema.asDynamicValue())

        elif self.kind is Schema.Kind.ENUM:
            LOG.debug('construct enum schema: %s', self._proto)
            self._schema = schema.asEnum()
            self.enumerants = tuple(map(
                Enumerant, self._schema.getEnumerants()))
            self._dict = {
                enumerant.name: enumerant for enumerant in self.enumerants}

        elif self.kind is Schema.Kind.INTERFACE:
            LOG.debug('construct interface schema: %s', self._proto)
            self._schema = schema.asInterface()
            # TODO: Load interface schema data.

        elif self.kind is Schema.Kind.LIST:
            assert isinstance(schema, native.ListSchema)
            self._schema = schema
            self.element_type = Type(schemas, self._schema.getElementType())
            LOG.debug('construct schema for list of %s', self.element_type)

        elif self.kind is Schema.Kind.STRUCT:
            LOG.debug('construct struct schema: %s', self._proto)
            self._schema = schema.asStruct()
            self.fields = self._get_fields(schemas)
            self.union_fields = self._collect_fields(
                self._schema.getUnionFields())
            self.non_union_fields = self._collect_fields(
                self._schema.getNonUnionFields())
            self._dict = {field.name: field for field in self.fields}

        else:
            assert self.kind is Schema.Kind.OTHER
            LOG.debug('construct schema: %s', self._proto)
            self._schema = schema

    def __str__(self):
        if self.kind is Schema.Kind.LIST:
            return self.kind.name
        else:
            return str(self._proto)

    __repr__ = repr_object

    def __iter__(self):
        if self.kind is Schema.Kind.ENUM:
            yield from self.enumerants
        elif self.kind is Schema.Kind.STRUCT:
            yield from self.fields
        else:
            raise AssertionError('schema is not iterable: %r' % self)

    def __getitem__(self, name):
        assert self.kind in (Schema.Kind.ENUM, Schema.Kind.STRUCT)
        return self._dict[name]

    def _get_fields(self, schemas):
        fields = tuple(
            Field(schemas, field) for field in self._schema.getFields())
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


class Field:

    def __init__(self, schemas, field):
        self._field = field
        self._proto = self._field.getProto()
        self.name = self._proto.getName()
        self.index = self._field.getIndex()
        self.type = Type(schemas, self._field.getType())

    def __str__(self):
        return self.name

    __repr__ = repr_object


class Type:

    class Kind(enum.Enum):

        @classmethod
        def from_type(cls, type_):
            for kind in cls:
                if kind.predicate(type_):
                    return kind
            raise AssertionError('undefined type kind: %s' % type_)

        VOID = (native.Type.isVoid, Schema.Kind.OTHER, type(None))
        BOOL = (native.Type.isBool, Schema.Kind.PRIMITIVE, bool)
        INT8 = (native.Type.isInt8, Schema.Kind.PRIMITIVE, int)
        INT16 = (native.Type.isInt16, Schema.Kind.PRIMITIVE, int)
        INT32 = (native.Type.isInt32, Schema.Kind.PRIMITIVE, int)
        INT64 = (native.Type.isInt64, Schema.Kind.PRIMITIVE, int)
        UINT8 = (native.Type.isUInt8, Schema.Kind.PRIMITIVE, int)
        UINT16 = (native.Type.isUInt16, Schema.Kind.PRIMITIVE, int)
        UINT32 = (native.Type.isUInt32, Schema.Kind.PRIMITIVE, int)
        UINT64 = (native.Type.isUInt64, Schema.Kind.PRIMITIVE, int)
        FLOAT32 = (native.Type.isFloat32, Schema.Kind.PRIMITIVE, float)
        FLOAT64 = (native.Type.isFloat64, Schema.Kind.PRIMITIVE, float)
        TEXT = (native.Type.isText, Schema.Kind.BLOB, str)
        DATA = (native.Type.isData, Schema.Kind.BLOB, bytes)
        LIST = (native.Type.isList, Schema.Kind.LIST, list)
        ENUM = (native.Type.isEnum, Schema.Kind.ENUM, enum.Enum)
        STRUCT = (native.Type.isStruct, Schema.Kind.STRUCT, object)
        INTERFACE = (native.Type.isInterface, Schema.Kind.INTERFACE, object)
        ANY_POINTER = (native.Type.isAnyPointer, Schema.Kind.OTHER, object)

        def __init__(self, predicate, schema_kind, python_type):
            self.predicate = predicate
            self.schema_kind = schema_kind
            self.python_type = python_type

    @staticmethod
    def _make_schema(schemas, schema):
        if isinstance(schema, native.ListSchema):
            node_id = _get_list_type_id(schema)
        else:
            node_id = schema.getProto().getId()
        if node_id in schemas:
            return schemas[node_id]
        else:
            schema = Schema(schemas, schema)
            assert node_id == schema.id
            schemas[node_id] = schema
            return schema

    def __init__(self, schemas, type_):
        self._type = type_
        self.kind = Type.Kind.from_type(self._type)

        if self.kind is Type.Kind.ENUM:
            self.schema = self._make_schema(schemas, self._type.asEnum())
        elif self.kind is Type.Kind.INTERFACE:
            self.schema = self._make_schema(schemas, self._type.asInterface())
        elif self.kind is Type.Kind.LIST:
            self.schema = self._make_schema(schemas, self._type.asList())
        elif self.kind is Type.Kind.STRUCT:
            self.schema = self._make_schema(schemas, self._type.asStruct())
        else:
            self.schema = None

    def __str__(self):
        return self.kind.name

    __repr__ = repr_object


class Value:

    def __init__(self, value):
        self._value = value


def _get_list_type_id(schema):
    # ListSchema is different - it doesn't has a Node.
    assert isinstance(schema, native.ListSchema)
    type_ = schema.getElementType()
    level = 0
    while type_.isList():
        type_ = type_.asList().getElementType()
        level += 1
    return (level, type_.hashCode())
