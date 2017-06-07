__all__ = [
    'Schema',
    'SchemaLoader',
]

from collections import OrderedDict
import enum
import logging

from . import bases
from . import io
from . import native


LOG = logging.getLogger(__name__)


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

    def load_bytes(self, blob):
        """Load schema from a binary blob in memory."""
        with io.make_bytes_reader(blob) as reader:
            self._load_schema(reader)

    def load_packed_bytes(self, blob):
        """Load schema from a packed binary blob in memory."""
        with io.make_packed_bytes_reader(blob) as reader:
            self._load_schema(reader)

    def load_file(self, path):
        """Load schema from a file."""
        with io.make_file_reader(path) as reader:
            self._load_schema(reader)

    def load_packed_file(self, path):
        """Load schema from a file whose contents are packed."""
        with io.make_packed_file_reader(path) as reader:
            self._load_schema(reader)

    def _load_schema(self, reader):
        assert self._loader is not None
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

    __repr__ = bases.repr_object


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
            self.id = bases.list_schema_id(schema)
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
            self._reverse_lookup = {
                enumerant.ordinal: enumerant
                for enumerant in self.enumerants
            }

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
            return 'List<%s>' % self.element_type
        else:
            return str(self._proto)

    __repr__ = bases.repr_object

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

    def get_enumerant_from_ordinal(self, ordinal):
        assert self.kind is Schema.Kind.ENUM
        return self._reverse_lookup.get(ordinal)

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
        self.ordinal = self._enumerant.getOrdinal()
        self.index = self._enumerant.getIndex()
        self.annotations = tuple(map(Annotation, self._proto.getAnnotations()))

    def __str__(self):
        return self.name

    __repr__ = bases.repr_object


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

    __repr__ = bases.repr_object


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
        if self.kind is Annotation.Kind.UNIDENTIFIED:
            return '$%s(%s)' % (self.id, self.value)
        else:
            return '$%s(%s)' % (self.kind.name, self.value)

    __repr__ = bases.repr_object


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
            node_id = bases.list_schema_id(schema)
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

    __repr__ = bases.repr_object


class Value:
    """Represent Value struct of schema.capnp.

    Don't confuse this with capnp::DynamicValue.
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
        return bases.str_value(self.get())

    __repr__ = bases.repr_object
