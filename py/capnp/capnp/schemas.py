"""Wrap capnp classes and provide Pythonic API.

Within Cap'n Proto's class hierarchy, it seems to have two levels of
classes, grouped in two namespace capnp and capnp::schema.  The first
group is at higher level that is based on the second group, which is
generated from capnp/schema.capnp directly.

If a class wraps a first-group C++ class, it usually has a reference to
another class that wraps the associated second-group C++ class; for
example, Schema wraps capnp::Schema, and it has a reference `_proto` to
Node, which wraps capnp::schema::Node associated with capnp::Schema.
"""

__all__ = [
    'SchemaLoader',

    'Enumerant',
    'Field',
    'Schema',

    'AnnotationDef',
    'FileNode',
    'Node',

    'Annotation',
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
    definitions are referenced from `definitions` (this is useful when
    you want to generate Python classes from the schema file).
    """

    class _StateUpdate:

        def __init__(self):

            self.files = OrderedDict()

            self.schemas = OrderedDict()
            self.definitions = []
            self.schema_lookup_table = {}

            self.annotations = OrderedDict()

            self.node_ids = set()

    def __init__(self):

        self._loader = None

        self.files = OrderedDict()

        # All schema definitions.
        self.schemas = OrderedDict()
        # Top-level schemas.
        self.definitions = []
        # Look up schema by fully-qualified name.
        self._schema_lookup_table = {}

        # Annotation definitions.
        self.annotations = OrderedDict()

        self._node_ids = set()

        self._update = None

    def open(self):
        assert self._loader is None
        self._loader = native.SchemaLoader()

    def close(self):
        self._loader, loader = None, self._loader
        loader._reset()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

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
                    # Skip it if it's branded (we only generate entry
                    # for the non-branded generic) to avoid duplicates.
                    if schema.is_branded:
                        continue
                elif schema.kind in (Schema.Kind.CONST, Schema.Kind.ENUM):
                    pass
                else:
                    continue
                fqname = self._get_fqname(schema)
                assert fqname not in self._schema_lookup_table
                LOG.debug('create look-up entry: %s -> %r', fqname, schema)
                self._schema_lookup_table[fqname] = schema

            # Commit changes.
            self.files.update(self._update.files)
            self.schemas.update(self._update.schemas)
            self.definitions.extend(self._update.definitions)
            self._schema_lookup_table.update(self._update.schema_lookup_table)
            self.annotations.update(self._update.annotations)
            self._node_ids.update(self._update.node_ids)

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
            self._get_or_add_annotation_def(node_id)

        elif node.isFile():
            file_node = FileNode(self, node)
            assert node_id == file_node.id
            assert not self._is_file_id(node_id)
            self._update.files[node_id] = file_node

        else:
            schema = self._get_or_add_schema(
                bases.get_schema_id(raw_schema),
                raw_schema,
            )
            if depth == 1:  # Collect top-level definitions.
                self._update.definitions.append(schema)

        for nested_node in node.getNestedNodes():
            self._load(nested_node.getId(), depth + 1)
        for annotation in node.getAnnotations():
            self._load(annotation.getId(), depth + 1)

    def _is_file_id(self, node_id):
        assert self._update is not None
        return node_id in self._update.files or node_id in self.files

    def _get_file(self, node_id):
        assert self._update is not None
        return bases.dicts_get((self._update.files, self.files), node_id)

    def _get_or_add_annotation_def(self, node_id):
        assert self._update is not None

        annotation_def = bases.dicts_get(
            (self._update.annotations, self.annotations),
            node_id
        )
        if annotation_def is not None:
            return annotation_def

        self._update.annotations[node_id] = annotation_def = AnnotationDef(
            self,
            self._loader.get(node_id).getProto(),
        )

        return annotation_def

    def _get_schema(self, schema_id):
        assert self._update is not None
        return bases.dicts_get((self._update.schemas, self.schemas), schema_id)

    def _get_or_add_schema(self, schema_id, raw_schema):
        assert self._update is not None

        schema = bases.dicts_get(
            (self._update.schemas, self.schemas),
            schema_id,
        )
        if schema is not None:
            return schema

        schema = Schema(self, raw_schema)
        assert schema_id == schema.id
        assert schema_id not in self._update.schemas
        LOG.debug('add schema: %s -> %s', schema_id, schema)
        self._update.schemas[schema_id] = schema

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
            known = annotation.node.known
            if known is AnnotationDef.Known.CXX_NAMESPACE:
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
    """Represent low-level capnp::schema::Node object.

    You usually don't need to access this, but other classes that wrap
    this and expose higher-level interface.
    """

    class Kind(enum.Enum):

        FILE = (native.schema.Node.Which.FILE,)
        STRUCT = (native.schema.Node.Which.STRUCT,)
        ENUM = (native.schema.Node.Which.ENUM,)
        INTERFACE = (native.schema.Node.Which.INTERFACE,)
        CONST = (native.schema.Node.Which.CONST,)
        ANNOTATION = (native.schema.Node.Which.ANNOTATION,)

        def __init__(self, which):
            self.which = which

    _KIND_LOOKUP = {kind.which: kind for kind in Kind}

    class NestedNode:

        def __init__(self, name, id_):
            self.name = name
            self.id = id_

    def __init__(self, loader, node):
        self._node = node
        self.id = self._node.getId()
        self.scope_id = self._node.getScopeId()
        self.kind = Node._KIND_LOOKUP[self._node.which()]
        self.name = self._node.getDisplayName()
        self.is_generic = self._node.getIsGeneric()
        self.nested_nodes = tuple(
            Node.NestedNode(nested_node.getName(), nested_node.getId())
            for nested_node in self._node.getNestedNodes()
        )
        self.annotations = tuple(
            Annotation(loader, annotation)
            for annotation in self._node.getAnnotations()
        )

    def __str__(self):
        return self.name

    __repr__ = bases.repr_object


class FileNode(Node):

    def __init__(self, loader, node):
        assert node.isFile()
        super().__init__(loader, node)
        LOG.debug('construct file node: %s', self.name)


class AnnotationDef(Node):
    """Represent a definition of annotation (not an use of annotation)."""

    class Known(enum.Enum):
        """Enumerate some well-known / built-in annotations."""

        # Annotation node id from capnp/c++.capnp.
        CXX_NAMESPACE = 0xb9c6f99ebf805f2c
        CXX_NAME = 0xf264a779fef191ce

    def __init__(self, loader, node):
        assert node.isAnnotation()
        super().__init__(loader, node)
        self.type = Type(
            loader,
            _schema_type_to_type(
                loader,
                self._node.getAnnotation().getType(),
            ),
        )
        try:
            self.known = self.Known(self.id)
        except ValueError:
            self.known = None
        LOG.debug('construct annotation node: %s', self.name)


class Schema:
    """Represent schema for various kind of entities.

    Schema has a two generic properties: `id` and `kind`.
    * `id` is unique among all schemas and is the key of the `schemas`
      of SchemaLoader.
    * `kind` describes the specific details of this Schema object.
    """

    class Kind(enum.Enum):

        ENUM = (Node.Kind.ENUM,)
        CONST = (Node.Kind.CONST,)
        INTERFACE = (Node.Kind.INTERFACE,)
        STRUCT = (Node.Kind.STRUCT,)

        LIST = (None,)  # ListSchema is not associated with a node.

        def __init__(self, node_kind):
            self.node_kind = node_kind

    _KIND_LOOKUP = {kind.node_kind: kind for kind in Kind if kind.node_kind}

    def __init__(self, loader, schema):

        self.id = bases.get_schema_id(schema)

        if isinstance(schema, native.ListSchema):
            self._proto = None
            self.kind = Schema.Kind.LIST
            self.name = None
        else:
            self._proto = Node(loader, schema.getProto())
            self.kind = Schema._KIND_LOOKUP[self._proto.kind]
            node = loader._loader.get(self._proto.scope_id).getProto()
            for nn in node.getNestedNodes():
                if nn.getId() == self._proto.id:
                    self.name = nn.getName()
                    break
            else:
                # This is probably a union field, which may be nameless.
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
            LOG.debug('construct list schema: List(%s)', self.element_type)

        elif self.kind is Schema.Kind.STRUCT:
            LOG.debug('construct struct schema: %s', self._proto)

            self._schema = schema.asStruct()

            self.is_generic = self._proto.is_generic
            self.is_branded = self._schema.isBranded()
            if self.is_branded:
                balist = self._schema.getBrandArgumentsAtScope(self._proto.id)
                self.brands = tuple(
                    Type(loader, balist[i])
                    for i in range(balist.size())
                )
            else:
                self.brands = ()

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
            if self.kind is Schema.Kind.STRUCT and self.is_branded:
                return '%s(%s)' % (self.name, ', '.join(map(str, self.brands)))
            else:
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
        self.annotations = tuple(
            Annotation(loader, annotation)
            for annotation in self._proto.getAnnotations()
        )

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
    """Represent an instance of annotation (not a definition)."""

    def __init__(self, loader, annotation):
        self._annotation = annotation
        self.id = self._annotation.getId()
        self.node = loader._get_or_add_annotation_def(self.id)
        self.value = _schema_value_to_python(
            self.node.type.schema,
            self._annotation.getValue(),
        )

    def __str__(self):
        if self.node.known:
            name = self.node.known.name
        else:
            name = self.node.name
        return '$%s(%s)' % (name, bases.str_value(self.value))

    __repr__ = bases.repr_object


class Type:
    """Wrap a capnp::Type object.

    Don't confuse it with capnp::schema::Type.
    """

    class Kind(enum.Enum):

        # display_name, which, is_scalar

        VOID = ('Void', native.schema.Type.Which.VOID, False)

        BOOL = ('Bool', native.schema.Type.Which.BOOL, True)
        INT8 = ('Int8', native.schema.Type.Which.INT8, True)
        INT16 = ('Int16', native.schema.Type.Which.INT16, True)
        INT32 = ('Int32', native.schema.Type.Which.INT32, True)
        INT64 = ('Int64', native.schema.Type.Which.INT64, True)
        UINT8 = ('UInt8', native.schema.Type.Which.UINT8, True)
        UINT16 = ('UInt16', native.schema.Type.Which.UINT16, True)
        UINT32 = ('UInt32', native.schema.Type.Which.UINT32, True)
        UINT64 = ('UInt64', native.schema.Type.Which.UINT64, True)
        FLOAT32 = ('Float32', native.schema.Type.Which.FLOAT32, True)
        FLOAT64 = ('Float64', native.schema.Type.Which.FLOAT64, True)

        TEXT = ('Text', native.schema.Type.Which.TEXT, True)
        DATA = ('Data', native.schema.Type.Which.DATA, True)

        LIST = ('List', native.schema.Type.Which.LIST, False)

        ENUM = ('enum', native.schema.Type.Which.ENUM, True)

        STRUCT = ('struct', native.schema.Type.Which.STRUCT, False)

        INTERFACE = ('interface', native.schema.Type.Which.INTERFACE, False)

        ANY_POINTER = (
            'AnyPointer', native.schema.Type.Which.ANY_POINTER, False)

        def __init__(self, display_name, which, is_scalar):
            self.display_name = display_name
            self.which = which
            self.is_scalar = is_scalar

    _KIND_LOOKUP = {kind.which: kind for kind in Kind}

    @staticmethod
    def _make_schema(loader, schema):
        return loader._get_or_add_schema(bases.get_schema_id(schema), schema)

    def __init__(self, loader, type_):
        self._type = type_
        self.kind = Type._KIND_LOOKUP[self._type.which()]

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
            return self.kind.display_name

    __repr__ = bases.repr_object


_SCHEMA_TYPE_PRIMITIVES = frozenset((
    native.schema.Type.Which.VOID,
    native.schema.Type.Which.BOOL,
    native.schema.Type.Which.INT8,
    native.schema.Type.Which.INT16,
    native.schema.Type.Which.INT32,
    native.schema.Type.Which.INT64,
    native.schema.Type.Which.UINT8,
    native.schema.Type.Which.UINT16,
    native.schema.Type.Which.UINT32,
    native.schema.Type.Which.UINT64,
    native.schema.Type.Which.FLOAT32,
    native.schema.Type.Which.FLOAT64,
    native.schema.Type.Which.TEXT,
    native.schema.Type.Which.DATA,
))


def _schema_type_to_type(loader, stype):
    """Convert capnp::schema::Type to capnp::Type object."""
    if stype.isEnum():
        return native.Type.fromEnumSchema(
            loader._loader
            .get(stype.getEnum().getTypeId())
            .asEnum()
        )
    elif stype.isStruct():
        return native.Type.fromStructSchema(
            loader._loader
            .get(stype.getStruct().getTypeId())
            .asStruct()
        )
    elif stype.which() in _SCHEMA_TYPE_PRIMITIVES:
        return native.Type.fromPrimitiveWhich(stype.which())
    else:
        raise AssertionError('unsupported conversion from: %s' % stype)


# which -> type_kind, python_type, hazzer, getter
_SCHEMA_VALUE_TABLE = {

    native.schema.Value.Which.VOID: (
        Type.Kind.VOID, type(None), None, lambda _: None,
    ),

    native.schema.Value.Which.BOOL: (
        Type.Kind.BOOL, bool, None, native.schema.Value.getBool,
    ),

    native.schema.Value.Which.INT8: (
        Type.Kind.INT8, int, None, native.schema.Value.getInt8,
    ),
    native.schema.Value.Which.INT16: (
        Type.Kind.INT16, int, None, native.schema.Value.getInt16,
    ),
    native.schema.Value.Which.INT32: (
        Type.Kind.INT32, int, None, native.schema.Value.getInt32,
    ),
    native.schema.Value.Which.INT64: (
        Type.Kind.INT64, int, None, native.schema.Value.getInt64,
    ),

    native.schema.Value.Which.UINT8: (
        Type.Kind.UINT8, int, None, native.schema.Value.getUint8,
    ),
    native.schema.Value.Which.UINT16: (
        Type.Kind.UINT16, int, None, native.schema.Value.getUint16,
    ),
    native.schema.Value.Which.UINT32: (
        Type.Kind.UINT32, int, None, native.schema.Value.getUint32,
    ),
    native.schema.Value.Which.UINT64: (
        Type.Kind.UINT64, int, None, native.schema.Value.getUint64,
    ),

    native.schema.Value.Which.FLOAT32: (
        Type.Kind.FLOAT32, float, None, native.schema.Value.getFloat32,
    ),
    native.schema.Value.Which.FLOAT64: (
        Type.Kind.FLOAT64, float, None, native.schema.Value.getFloat64,
    ),

    native.schema.Value.Which.TEXT: (
        Type.Kind.TEXT, str,
        native.schema.Value.hasText, native.schema.Value.getText,
    ),
    native.schema.Value.Which.DATA: (
        Type.Kind.DATA, bytes,
        native.schema.Value.hasData, native.schema.Value.getData,
    ),

    native.schema.Value.Which.LIST: (
        Type.Kind.LIST, tuple,
        native.schema.Value.hasList, native.schema.Value.getList,
    ),

    native.schema.Value.Which.ENUM: (
        Type.Kind.ENUM, int, None, native.schema.Value.getEnum,
    ),

    native.schema.Value.Which.STRUCT: (
        Type.Kind.STRUCT, object,
        native.schema.Value.hasStruct, native.schema.Value.getStruct,
    ),

    native.schema.Value.Which.INTERFACE: (
        Type.Kind.INTERFACE, type(None), None, lambda _: None,
    ),

    native.schema.Value.Which.ANY_POINTER: (
        Type.Kind.ANY_POINTER, object,
        native.schema.Value.hasAnyPointer, native.schema.Value.getAnyPointer,
    ),
}


def _schema_value_to_python(schema, value, default=None):
    """Convert capnp::schema::Value to a Python object.

    Don't confuse it with capnp::DynamicValue.
    """

    which = value.which()
    if which not in _SCHEMA_VALUE_TABLE:
        raise AssertionError('unsupported schema value: %s' % value)
    type_kind, python_type, hazzer, getter = _SCHEMA_VALUE_TABLE[which]

    if hazzer and not hazzer(value):
        return default

    python_value = getter(value)

    if type_kind is Type.Kind.LIST:
        assert schema is not None
        python_type = dynamics.DynamicList
        python_value = dynamics.DynamicList(
            schema,
            python_value.getAsList(schema._schema),
        )

    elif type_kind is Type.Kind.STRUCT:
        assert schema is not None
        python_type = dynamics.DynamicStruct
        python_value = dynamics.DynamicStruct(
            schema,
            python_value.getAsStruct(schema._schema),
        )

    elif type_kind is Type.Kind.ANY_POINTER:
        python_type = dynamics.AnyPointer
        python_value = dynamics.AnyPointer(python_value)

    assert isinstance(python_value, python_type)

    return python_value
