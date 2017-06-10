__all__ = [
    'Annotation',
    'Schema',
    'SchemaLoader',
    'Type',
]

from collections import OrderedDict
import enum
import logging

from . import bases
from . import dynamics  # Cyclic dependency :(
from . import io
from . import native


LOG = logging.getLogger(__name__)


class SchemaLoader:
    """Load Cap'n Proto schema.

    The loaded schemas are stored in `schemas`.  Also, top-level
    declarations are referenced from `declarations` (this is useful when
    you want to generate Python classes from the schema file).
    """

    class _StateUpdate:

        def __init__(self):
            self.files = OrderedDict()
            self.schemas = OrderedDict()
            self.declarations = []
            self.node_ids = set()
            self.schema_lookup_table = {}

    def __init__(self):

        self._loader = None

        self.files = OrderedDict()
        self.schemas = OrderedDict()
        self.declarations = []  # Top-level declarations.
        self._node_ids = set()
        self._schema_lookup_table = {}

        self._update = None

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

    def load_file(self, path):
        """Load schema from a file."""
        with io.make_file_reader(path) as reader:
            self._load_schema(reader)

    def _load_schema(self, reader):
        assert self._loader is not None
        assert self._update is None

        codegen_request = reader.getRoot()

        for node in codegen_request.getNodes():
            self._loader.load(node)

        # Implement transaction semantics.
        self._update = self._StateUpdate()
        try:

            for requested_file in codegen_request.getRequestedFiles():
                self._load(requested_file.getId(), 0)

            # Create look-up entry for const, enum, and struct.
            for schema in self._update.schemas.values():
                if schema.kind is Schema.Kind.STRUCT:
                    # Skip it if it's a union field.
                    if schema._proto._node.getStruct().getIsGroup():
                        continue
                elif schema.kind in (Schema.Kind.CONST, Schema.Kind.ENUM):
                    pass
                else:
                    continue
                fqname = self._get_fqname(schema)
                LOG.debug('create look-up entry: %s -> %r', fqname, schema)
                self._schema_lookup_table[fqname] = schema

            # Commit changes.
            self.files.update(self._update.files)
            self.schemas.update(self._update.schemas)
            self.declarations.extend(self._update.declarations)
            self._node_ids.update(self._update.node_ids)
            self._schema_lookup_table.update(self._update.schema_lookup_table)

        finally:
            self._update = None

    def _load(self, node_id, depth):
        """Recursively traverse and load nodes."""

        if node_id in self._update.node_ids or node_id in self._node_ids:
            return

        self._update.node_ids.add(node_id)

        raw_schema = self._loader.get(node_id)
        node = raw_schema.getProto()

        if node.isAnnotation():
            pass  # We don't track annotation definitions, yet.

        elif node.isFile():
            file_node = FileNode(node)
            assert node_id == file_node.id
            assert not self._is_file_id(node_id)
            self._update.files[node_id] = file_node

        else:
            schema = self._get_or_add_schema(node_id, raw_schema)
            if depth == 1:  # Collect top-level declarations.
                self._update.declarations.append(schema)

        for nested_node in node.getNestedNodes():
            self._load(nested_node.getId(), depth + 1)
        for annotation in node.getAnnotations():
            self._load(annotation.getId(), depth + 1)

    def _is_file_id(self, node_id):
        assert self._update is not None
        return node_id in self._update.files or node_id in self.files

    def _get_file(self, node_id):
        assert self._update is not None
        return self._update.files.get(node_id) or self.files.get(node_id)

    def _get_schema(self, node_id):
        assert self._update is not None
        return self._update.schemas.get(node_id) or self.schemas.get(node_id)

    def _get_or_add_schema(self, node_id, raw_schema):
        assert self._update is not None
        schema = self._update.schemas.get(node_id) or self.schemas.get(node_id)
        if schema is not None:
            return schema
        schema = Schema(self, raw_schema)
        assert node_id == schema.id
        assert node_id not in self._update.schemas
        self._update.schemas[node_id] = schema
        return schema

    def _get_fqname(self, schema):
        assert schema.name is not None

        parts = [schema.name]
        while True:
            next_schema = self._get_schema(schema._proto.scope_id)
            if next_schema is None:
                break
            assert next_schema.name is not None
            schema = next_schema
            parts.append(schema.name)
        qual_name = '.'.join(reversed(parts))

        file_node = self._get_file(schema._proto.scope_id)
        assert file_node is not None
        module_name = None
        for annotation in file_node.annotations:
            if annotation.kind is Annotation.Kind.CXX_NAMESPACE:
                module_name = annotation.value.replace('::', '.').strip('.')
                break
        else:
            raise ValueError(
                'file is not annotated with namespace: %s' % file_node)

        return '%s:%s' % (module_name, qual_name)

    def get_schema(self, fqname):
        """Get schema by fully-qualified name."""
        return self._schema_lookup_table.get(fqname)


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

    class NestedNode:

        def __init__(self, name, id_):
            self.name = name
            self.id = id_

    def __init__(self, node):
        assert not node.getIsGeneric(), 'do not support generics yet'
        self._node = node
        self.id = self._node.getId()
        self.scope_id = self._node.getScopeId()
        self.kind = Node.Kind.from_node(self._node)
        self.name = self._node.getDisplayName()
        self.nested_nodes = tuple(
            Node.NestedNode(nested_node.getName(), nested_node.getId())
            for nested_node in self._node.getNestedNodes()
        )
        self.annotations = tuple(map(Annotation, self._node.getAnnotations()))

    def __str__(self):
        return self.name

    __repr__ = bases.repr_object


class FileNode(Node):

    def __init__(self, node):
        assert node.isFile()
        super().__init__(node)


class Schema:
    """Represent schema for various kind of entities.

    Schema has a two generic properties: `id` and `kind`.
    * `id` is unique among all schemas and is the key of the
      `schemas` of SchemaLoader.
    * `kind` describes the specific details of this Schema object.
    """

    class Kind(enum.Enum):

        @classmethod
        def from_node(cls, node):
            if node.kind is Node.Kind.CONST:
                return cls.CONST
            elif node.kind is Node.Kind.ENUM:
                return cls.ENUM
            elif node.kind is Node.Kind.INTERFACE:
                return cls.INTERFACE
            elif node.kind is Node.Kind.STRUCT:
                return cls.STRUCT
            else:
                raise AssertionError('unrecognizable schema type: %s' % node)

        ENUM = enum.auto()
        CONST = enum.auto()
        INTERFACE = enum.auto()
        LIST = enum.auto()
        STRUCT = enum.auto()

    def __init__(self, loader, schema):

        if isinstance(schema, native.ListSchema):
            self._proto = None
            self.id = bases.list_schema_id(schema)
            self.kind = Schema.Kind.LIST
            self.name = None
        else:
            self._proto = Node(schema.getProto())
            self.id = self._proto.id
            self.kind = Schema.Kind.from_node(self._proto)
            node = loader._loader.get(self._proto.scope_id).getProto()
            for nn in node.getNestedNodes():
                if nn.getId() == self.id:
                    self.name = nn.getName()
                    break
            else:
                # This is probably a union field, which does not have a
                # name in usual sense.
                self.name = None

        if self.kind is Schema.Kind.CONST:
            LOG.debug('construct const schema: %s', self._proto)
            self._schema = schema.asConst()
            self.type = Type(loader, self._schema.getType())
            self.value = dynamics._dynamic_value_reader_to_python(
                self.type,
                self._schema.asDynamicValue(),
            )

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
            self.element_type = Type(loader, self._schema.getElementType())
            LOG.debug('construct schema for list of %s', self.element_type)

        elif self.kind is Schema.Kind.STRUCT:
            LOG.debug('construct struct schema: %s', self._proto)
            self._schema = schema.asStruct()
            self.fields = self._get_fields(loader)
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

    @property
    def annotations(self):
        assert self.kind is not Schema.Kind.LIST
        return self._proto.annotations

    def __str__(self):
        if self.kind is Schema.Kind.LIST:
            return 'List(%s)' % self.element_type
        elif self.name is not None:
            return self.name
        else:
            return str(self._proto)

    __repr__ = bases.repr_object

    def __len__(self):
        assert self.kind in (Schema.Kind.ENUM, Schema.Kind.STRUCT)
        return len(self._dict)

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

    def generate_enum(self, name_fixes=None):
        """Generate enum.Enum class from this EnumSchema.

        The camelCase member name will be replaced with SNAKE_CASE one.

        If the SNAKE_CASE transformation is messed up, you may override
        it with the name_fixes dict.
        """
        assert self.kind is Schema.Kind.ENUM
        assert self.name is not None
        name_fixes = name_fixes or {}
        return enum.Enum(self.name, [
            (
                name_fixes.get(
                    enumerant.name,
                    bases.camel_to_upper_snake(enumerant.name),
                ),
                enumerant.ordinal,
            )
            for enumerant in self.enumerants
        ])

    def get_enumerant_from_ordinal(self, ordinal):
        assert self.kind is Schema.Kind.ENUM
        return self._reverse_lookup.get(ordinal)

    def _get_fields(self, loader):
        fields = tuple(
            Field(loader, field)
            for field in self._schema.getFields()
        )
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
        self.annotations = tuple(map(Annotation, self._proto.getAnnotations()))

    def __str__(self):
        return self.name

    __repr__ = bases.repr_object


class Field:

    def __init__(self, loader, field):
        self._field = field
        self._proto = self._field.getProto()
        self.name = self._proto.getName()
        self.index = self._field.getIndex()
        self.type = Type(loader, self._field.getType())
        self.annotations = tuple(map(Annotation, self._proto.getAnnotations()))

        if self._proto.isSlot():
            slot = self._proto.getSlot()
            self.has_explicit_default = slot.getHadExplicitDefault()
            if self.has_explicit_default:
                self.explicit_default = _schema_value_to_python(
                    self.type.schema,
                    slot.getDefaultValue(),
                )
            else:
                self.explicit_default = None
        else:
            self.has_explicit_default = False
            self.explicit_default = None

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
        self.kind = Annotation.Kind.from_id(self.id)
        self.value = _schema_value_to_python(
            None,  # TODO: Look up its type and schema.
            self._annotation.getValue(),
        )

    def __str__(self):
        if self.kind is Annotation.Kind.UNIDENTIFIED:
            return '$%s(%s)' % (self.id, bases.str_value(self.value))
        else:
            return '$%s(%s)' % (self.kind.name, bases.str_value(self.value))

    __repr__ = bases.repr_object


class Type:

    class Kind(enum.Enum):

        @classmethod
        def from_type(cls, type_):
            for kind in cls:
                if kind.izzer(type_):
                    return kind
            raise AssertionError('undefined type kind: %s' % type_)

        # izzer, is_scalar
        VOID = (native.Type.isVoid, False)

        BOOL = (native.Type.isBool, True)
        INT8 = (native.Type.isInt8, True)
        INT16 = (native.Type.isInt16, True)
        INT32 = (native.Type.isInt32, True)
        INT64 = (native.Type.isInt64, True)
        UINT8 = (native.Type.isUInt8, True)
        UINT16 = (native.Type.isUInt16, True)
        UINT32 = (native.Type.isUInt32, True)
        UINT64 = (native.Type.isUInt64, True)
        FLOAT32 = (native.Type.isFloat32, True)
        FLOAT64 = (native.Type.isFloat64, True)

        TEXT = (native.Type.isText, True)
        DATA = (native.Type.isData, True)

        LIST = (native.Type.isList, False)

        ENUM = (native.Type.isEnum, True)

        STRUCT = (native.Type.isStruct, False)

        INTERFACE = (native.Type.isInterface, False)

        ANY_POINTER = (native.Type.isAnyPointer, False)

        def __init__(self, izzer, is_scalar):
            self.izzer = izzer
            self.is_scalar = is_scalar

    @staticmethod
    def _make_schema(loader, schema):
        if isinstance(schema, native.ListSchema):
            node_id = bases.list_schema_id(schema)
        else:
            node_id = schema.getProto().getId()
        return loader._get_or_add_schema(node_id, schema)

    def __init__(self, loader, type_):
        self._type = type_
        self.kind = Type.Kind.from_type(self._type)

        if self.kind is Type.Kind.ENUM:
            self.schema = self._make_schema(loader, self._type.asEnum())
        elif self.kind is Type.Kind.INTERFACE:
            self.schema = self._make_schema(loader, self._type.asInterface())
        elif self.kind is Type.Kind.LIST:
            self.schema = self._make_schema(loader, self._type.asList())
        elif self.kind is Type.Kind.STRUCT:
            self.schema = self._make_schema(loader, self._type.asStruct())
        else:
            self.schema = None

    def __str__(self):
        if self.kind is Type.Kind.LIST:
            return 'List(%s)' % self.schema.element_type
        elif self.schema is not None:
            return str(self.schema)
        else:
            return self.kind.name

    __repr__ = bases.repr_object


# type_kind, python_type, izzer, hazzer, getter
_SCHEMA_VALUE_TABLE = (

    (
        Type.Kind.VOID,
        type(None),
        native.schema.Value.isVoid, None, lambda _: None,
    ),

    (
        Type.Kind.BOOL,
        bool,
        native.schema.Value.isBool, None, native.schema.Value.getBool,
    ),

    (
        Type.Kind.INT8,
        int,
        native.schema.Value.isInt8, None, native.schema.Value.getInt8,
    ),
    (
        Type.Kind.INT16,
        int,
        native.schema.Value.isInt16, None, native.schema.Value.getInt16,
    ),
    (
        Type.Kind.INT32,
        int,
        native.schema.Value.isInt32, None, native.schema.Value.getInt32,
    ),
    (
        Type.Kind.INT64,
        int,
        native.schema.Value.isInt64, None, native.schema.Value.getInt64,
    ),

    (
        Type.Kind.UINT8,
        int,
        native.schema.Value.isUint8, None, native.schema.Value.getUint8,
    ),
    (
        Type.Kind.UINT16,
        int,
        native.schema.Value.isUint16, None, native.schema.Value.getUint16,
    ),
    (
        Type.Kind.UINT32,
        int,
        native.schema.Value.isUint32, None, native.schema.Value.getUint32,
    ),
    (
        Type.Kind.UINT64,
        int,
        native.schema.Value.isUint64, None, native.schema.Value.getUint64,
    ),

    (
        Type.Kind.FLOAT32,
        float,
        native.schema.Value.isFloat32, None, native.schema.Value.getFloat32,
    ),
    (
        Type.Kind.FLOAT64,
        float,
        native.schema.Value.isFloat64, None, native.schema.Value.getFloat64,
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
        Type.Kind.INTERFACE,
        type(None),
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


def _schema_value_to_python(schema, value, default=None):
    type_kind = python_type = izzer = hazzer = getter = None
    for type_kind, python_type, izzer, hazzer, getter in _SCHEMA_VALUE_TABLE:
        if izzer(value):
            break
    if type_kind is None:
        raise AssertionError('unsupported schema value: %s' % value)

    if hazzer and not hazzer(value):
        return default

    python_value = getter(value)

    if type_kind is Type.Kind.LIST:
        assert python_value.isList()
        # TODO: Remove this when Annotation looks up schema.
        assert schema is not None, 'cannot handle list annotation for now'
        python_type = dynamics.DynamicList
        python_value = dynamics.DynamicList(
            schema,
            python_value.getAsList(schema._schema),
        )

    elif type_kind is Type.Kind.STRUCT:
        assert python_value.isStruct()
        # TODO: Remove this when Annotation looks up schema.
        assert schema is not None, 'cannot handle struct annotation for now'
        python_type = dynamics.DynamicStruct
        python_value = dynamics.DynamicStruct(
            schema,
            python_value.getAsStruct(schema._schema),
        )

    elif type_kind is Type.Kind.ANY_POINTER:
        raise NotImplementedError  # TODO: Handle AnyPointer.

    assert isinstance(python_value, python_type)

    return python_value
