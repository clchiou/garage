"""Hand-written schema.capnp.c++ wrapper."""

__all__ = [
    'CodeGeneratorRequest',
]

from cpython.pycapsule cimport PyCapsule_New, PyCapsule_GetPointer
from cython.operator cimport dereference as deref, preincrement as inc
from libc.stdint cimport uint16_t, uint32_t, uint64_t
from libcpp cimport bool


cdef extern from 'schema.capnp.h' namespace 'capnp::schema':

    cdef cppclass _NestedNode 'capnp::schema::Node::NestedNode::Reader':

        bool hasName() except +
        const char* getName 'getName().cStr'() except +

        uint64_t getId() except +

    cdef cppclass _Value 'capnp::schema::Value::Reader':

        bool isText() except +
        bool hasText() except +
        const char* getText 'getText().cStr'() except +

    cdef cppclass _Annotation 'capnp::schema::Annotation::Reader':

        uint64_t getId() except +

        bool hasValue() except +
        _Value getValue() except +


cdef extern from 'capnp/list.h' namespace 'capnp':

    cdef cppclass Iterator_NestedNode 'capnp::List<capnp::schema::Node::NestedNode>::Reader::Iterator':
        bool operator!=(Iterator_NestedNode&)
        Iterator_NestedNode& operator++()
        _NestedNode operator*()

    cdef cppclass List_NestedNode 'capnp::List<capnp::schema::Node::NestedNode>::Reader':
        Iterator_NestedNode begin()
        Iterator_NestedNode end()

    cdef cppclass Iterator_Annotation 'capnp::List<capnp::schema::Annotation>::Reader::Iterator':
        bool operator!=(Iterator_Annotation&)
        Iterator_Annotation& operator++()
        _Annotation operator*()

    cdef cppclass List_Annotation 'capnp::List<capnp::schema::Annotation>::Reader':
        Iterator_Annotation begin()
        Iterator_Annotation end()

    cdef cppclass Iterator_Field 'capnp::List<capnp::schema::Field>::Reader::Iterator':
        bool operator!=(Iterator_Field&)
        Iterator_Field& operator++()
        _Field operator*()

    cdef cppclass List_Field 'capnp::List<capnp::schema::Field>::Reader':
        Iterator_Field begin()
        Iterator_Field end()


cdef extern from 'schema.capnp.h' namespace 'capnp::schema':

    cdef cppclass _Type 'capnp::schema::Type::Reader':

        bool isVoid() except +

        bool isBool() except +

        bool isInt8() except +
        bool isInt16() except +
        bool isInt32() except +
        bool isInt64() except +

        bool isUint8() except +
        bool isUint16() except +
        bool isUint32() except +
        bool isUint64() except +

        bool isFloat32() except +
        bool isFloat64() except +

        bool isText() except +

        bool isData() except +

        bool isList() except +
        bool hasElementType 'getList().hasElementType'() except +
        _Type getElementType 'getList().getElementType'() except +

        bool isEnum() except +
        uint64_t getEnumTypeId 'getEnum().getTypeId'() except +

        bool isStruct() except +
        uint64_t getStructTypeId 'getStruct().getTypeId'() except +

    cdef cppclass _Slot 'capnp::schema::Field::Slot::Reader':
        bool hasType() except +
        _Type getType() except +

    cdef cppclass _Group 'capnp::schema::Field::Group::Reader':
        uint64_t getTypeId() except +

    cdef cppclass _Field 'capnp::schema::Field::Reader':

        bool hasName() except +
        const char* getName 'getName().cStr'() except +

        uint16_t getCodeOrder() except +

        bool isSlot() except +
        _Slot getSlot() except +

        bool isGroup() except +
        _Group getGroup() except +

    cdef cppclass _Struct 'capnp::schema::Node::Struct::Reader':

        bool getIsGroup() except +

        bool hasFields() except +
        List_Field getFields() except +

    cdef cppclass _Enumerant 'capnp::schema::Enumerant::Reader':

        bool hasName() except +
        const char* getName 'getName().cStr'() except +

        uint16_t getCodeOrder() except +

    cdef cppclass _Const 'capnp::schema::Node::Const::Reader':

        bool hasType() except +
        _Type getType() except +

        bool hasValue() except +
        _Value getValue() except +

    cdef cppclass _Node 'capnp::schema::Node::Reader':

        uint64_t getId() except +

        bool hasDisplayName() except +
        const char* getDisplayName 'getDisplayName().cStr'() except +

        uint32_t getDisplayNamePrefixLength() except +

        uint64_t getScopeId() except +

        bool hasNestedNodes() except +
        List_NestedNode getNestedNodes() except +

        bool hasAnnotations() except +
        List_Annotation getAnnotations() except +

        bool isFile() except +

        bool isStruct() except +
        _Struct getStruct() except +

        bool isEnum() except +
        bool hasEnumerants 'getEnum().hasEnumerants'() except +
        List_Enumerant getEnumerants 'getEnum().getEnumerants'() except +

        bool isConst() except +
        _Const getConst() except +

    cdef cppclass _Import 'capnp::schema::CodeGeneratorRequest::RequestedFile::Import::Reader':

        uint64_t getId() except +

        bool hasName() except +
        const char* getName 'getName().cStr'() except +


cdef extern from 'capnp/list.h' namespace 'capnp':

    cdef cppclass Iterator_Enumerant 'capnp::List<capnp::schema::Enumerant>::Reader::Iterator':
        bool operator!=(Iterator_Enumerant&)
        Iterator_Enumerant& operator++()
        _Enumerant operator*()

    cdef cppclass List_Enumerant 'capnp::List<capnp::schema::Enumerant>::Reader':
        Iterator_Enumerant begin()
        Iterator_Enumerant end()

    cdef cppclass Iterator_Const 'capnp::List<capnp::schema::Node::Const>::Reader::Iterator':
        bool operator!=(Iterator_Const&)
        Iterator_Const& operator++()
        _Const operator*()

    cdef cppclass List_Const 'capnp::List<capnp::schema::Node::Const>::Reader':
        Iterator_Const begin()
        Iterator_Const end()

    cdef cppclass Iterator_Import 'capnp::List<capnp::schema::CodeGeneratorRequest::RequestedFile::Import>::Reader::Iterator':
        bool operator!=(Iterator_Import&)
        Iterator_Import& operator++()
        _Import operator*()

    cdef cppclass List_Import 'capnp::List<capnp::schema::CodeGeneratorRequest::RequestedFile::Import>::Reader':
        Iterator_Import begin()
        Iterator_Import end()


cdef extern from 'schema.capnp.h' namespace 'capnp::schema':

    cdef cppclass _RequestedFile 'capnp::schema::CodeGeneratorRequest::RequestedFile::Reader':

        uint64_t getId() except +

        bool hasFilename() except +
        const char* getFilename 'getFilename().cStr'() except +

        bool hasImports() except +
        List_Import getImports() except +


cdef extern from 'capnp/list.h' namespace 'capnp':

    cdef cppclass Iterator_Node 'capnp::List<capnp::schema::Node>::Reader::Iterator':
        bool operator!=(Iterator_Node&)
        Iterator_Node& operator++()
        _Node operator*()

    cdef cppclass List_Node 'capnp::List<capnp::schema::Node>::Reader':
        Iterator_Node begin()
        Iterator_Node end()

    cdef cppclass Iterator_RequestedFile 'capnp::List<capnp::schema::CodeGeneratorRequest::RequestedFile>::Reader::Iterator':
        bool operator!=(Iterator_RequestedFile&)
        Iterator_RequestedFile& operator++()
        _RequestedFile operator*()

    cdef cppclass List_RequestedFile 'capnp::List<capnp::schema::CodeGeneratorRequest::RequestedFile>::Reader':
        Iterator_RequestedFile begin()
        Iterator_RequestedFile end()


cdef extern from 'schema.capnp.h' namespace 'capnp::schema':

    cdef cppclass _CodeGeneratorRequest 'capnp::schema::CodeGeneratorRequest::Reader':

        bool hasNodes() except +
        List_Node getNodes() except +

        bool hasRequestedFiles() except +
        List_RequestedFile getRequestedFiles() except +


cdef extern from 'capnp/common.h' namespace 'capnp':

    cdef cppclass word:
        pass


cdef extern from 'kj/common.h' namespace 'kj':

    cdef cppclass ArrayPtr 'kj::ArrayPtr<const capnp::word>':
        ArrayPtr(const word* begin, size_t size) except +


cdef extern from 'capnp/serialize.h' namespace 'capnp':

    cdef cppclass FlatArrayMessageReader:

        FlatArrayMessageReader(ArrayPtr array) except +

        _CodeGeneratorRequest getRoot 'getRoot<capnp::schema::CodeGeneratorRequest>'() except +


cdef class CodeGeneratorRequest:

    cdef bytes _request_bytes
    cdef FlatArrayMessageReader *_reader
    cdef _CodeGeneratorRequest _request

    cdef tuple _nodes
    cdef tuple _requested_files

    def __cinit__(self, bytes request_bytes):

        self._request_bytes = request_bytes

        cdef const char* request_begin = request_bytes
        self._reader = new FlatArrayMessageReader(ArrayPtr(
            <word*>request_begin,
            len(request_bytes),
        ))

        self._request = self._reader.getRoot()

        self._nodes = None
        self._requested_files = None

    def __dealloc__(self):
        del self._reader

    def _asdict(self):
        return {
            'nodes': [
                node._asdict()
                for node in self.nodes or ()
            ],
            'requested_files': [
                requested_file._asdict()
                for requested_file in self.requested_files or ()
            ],
        }

    @property
    def nodes(self):
        if self._nodes is None and self._request.hasNodes():
            self._nodes = self._get_nodes()
        return self._nodes

    def _get_nodes(self):
        cdef List_Node _nodes = self._request.getNodes()
        cdef Iterator_Node begin = _nodes.begin()
        cdef Iterator_Node end = _nodes.end()
        cdef _Node _node
        nodes = []
        while begin != end:
            _node = deref(begin)
            nodes.append(Node(self, PyCapsule_New(&_node, NULL, NULL)))
            inc(begin)
        return tuple(nodes)

    @property
    def requested_files(self):
        if self._requested_files is None and self._request.hasRequestedFiles():
            self._requested_files = self._get_requested_files()
        return self._requested_files

    def _get_requested_files(self):
        cdef List_RequestedFile _requested_files = self._request.getRequestedFiles()
        cdef Iterator_RequestedFile begin = _requested_files.begin()
        cdef Iterator_RequestedFile end = _requested_files.end()
        cdef _RequestedFile _requested_file
        requested_files = []
        while begin != end:
            _requested_file = deref(begin)
            requested_files.append(RequestedFile(self, PyCapsule_New(&_requested_file, NULL, NULL)))
            inc(begin)
        return tuple(requested_files)


cdef class Node:

    cdef CodeGeneratorRequest _root
    cdef _Node _node

    cdef str _display_name
    cdef tuple _nested_nodes
    cdef tuple _annotations
    cdef tuple _fields
    cdef tuple _enumerants
    cdef Const _const

    def __cinit__(self, CodeGeneratorRequest root, object node):
        self._root = root
        self._node = deref(<_Node*>PyCapsule_GetPointer(node, NULL))

        self._display_name = None
        self._nested_nodes = None
        self._annotations = None
        self._fields = None
        self._enumerants = None
        self._const = None

    def _asdict(self):
        data = {
            'id': self.id,
            'display_name': self.display_name,
            'display_name_prefix_length': self.display_name_prefix_length,
            'scope_id': self.scope_id,
            'nested_nodes': [
                nested_node._asdict()
                for nested_node in self.nested_nodes or ()
            ],
            'annotations': [
                annotation._asdict()
                for annotation in self.annotations or ()
            ],
        }
        if self.is_file():
            data['file'] = None
        elif self.is_struct():
            data['struct'] = {
                'is_group': self.is_group(),
                'fields': [
                    field._asdict()
                    for field in self.fields or ()
                ],
            }
        elif self.is_enum():
            data['enum'] = [
                enumerant._asdict()
                for enumerant in self.enumerants or ()
            ]
        elif self.is_const():
            data['const'] = self.const._asdict()
        return data

    @property
    def id(self):
        return self._node.getId()

    @property
    def display_name(self):
        cdef bytes display_name_bytes
        if self._display_name is None and self._node.hasDisplayName():
            display_name_bytes = <bytes>self._node.getDisplayName()
            self._display_name = display_name_bytes.decode('utf8')
        return self._display_name

    @property
    def display_name_prefix_length(self):
        return self._node.getDisplayNamePrefixLength()

    @property
    def scope_id(self):
        return self._node.getScopeId()

    @property
    def nested_nodes(self):
        if self._nested_nodes is None and self._node.hasNestedNodes():
            self._nested_nodes = self._get_nested_nodes()
        return self._nested_nodes

    def _get_nested_nodes(self):
        cdef List_NestedNode _nested_nodes = self._node.getNestedNodes()
        cdef Iterator_NestedNode begin = _nested_nodes.begin()
        cdef Iterator_NestedNode end = _nested_nodes.end()
        cdef _NestedNode _nested_node
        nested_nodes = []
        while begin != end:
            _nested_node = deref(begin)
            nested_nodes.append(NestedNode(self._root, PyCapsule_New(&_nested_node, NULL, NULL)))
            inc(begin)
        return tuple(nested_nodes)

    @property
    def annotations(self):
        if self._annotations is None and self._node.hasAnnotations():
            self._annotations = self._get_annotations()
        return self._annotations

    def _get_annotations(self):
        cdef List_Annotation _annotations = self._node.getAnnotations()
        cdef Iterator_Annotation begin = _annotations.begin()
        cdef Iterator_Annotation end = _annotations.end()
        cdef _Annotation _annotation
        annotations = []
        while begin != end:
            _annotation = deref(begin)
            annotations.append(Annotation(self._root, PyCapsule_New(&_annotation, NULL, NULL)))
            inc(begin)
        return tuple(annotations)

    def is_file(self):
        return self._node.isFile()

    def is_struct(self):
        return self._node.isStruct()

    def is_group(self):
        return self._node.isStruct() and self._node.getStruct().getIsGroup()

    @property
    def fields(self):
        if self._fields is None and self._node.isStruct() and self._node.getStruct().hasFields():
            self._fields = self._get_fields()
        return self._fields

    def _get_fields(self):
        cdef List_Field _fields = self._node.getStruct().getFields()
        cdef Iterator_Field begin = _fields.begin()
        cdef Iterator_Field end = _fields.end()
        cdef _Field _field
        fields = []
        while begin != end:
            _field = deref(begin)
            fields.append(Field(self._root, PyCapsule_New(&_field, NULL, NULL)))
            inc(begin)
        return tuple(fields)

    def is_enum(self):
        return self._node.isEnum()

    @property
    def enumerants(self):
        if self._enumerants is None and self._node.isEnum() and self._node.hasEnumerants():
            self._enumerants = self._get_enumerants()
        return self._enumerants

    def _get_enumerants(self):
        cdef List_Enumerant _enumerants = self._node.getEnumerants()
        cdef Iterator_Enumerant begin = _enumerants.begin()
        cdef Iterator_Enumerant end = _enumerants.end()
        cdef _Enumerant _enumerant
        enumerants = []
        while begin != end:
            _enumerant = deref(begin)
            enumerants.append(Enumerant(self._root, PyCapsule_New(&_enumerant, NULL, NULL)))
            inc(begin)
        return tuple(enumerants)

    def is_const(self):
        return self._node.isConst()

    @property
    def const(self):
        cdef _Const _const
        if self._const is None and self._node.isConst():
            _const = self._node.getConst()
            self._const = Const(self._root, PyCapsule_New(&_const, NULL, NULL))
        return self._const


cdef class NestedNode:

    cdef CodeGeneratorRequest _root
    cdef _NestedNode _nested_node

    cdef str _name

    def __cinit__(self, CodeGeneratorRequest root, object nested_node):
        self._root = root
        self._nested_node = deref(<_NestedNode*>PyCapsule_GetPointer(nested_node, NULL))

        self._name = None

    def _asdict(self):
        return {
            'name': self.name,
            'id': self.id,
        }

    @property
    def name(self):
        cdef bytes name_bytes
        if self._name is None and self._nested_node.hasName():
            name_bytes = <bytes>self._nested_node.getName()
            self._name = name_bytes.decode('utf8')
        return self._name

    @property
    def id(self):
        return self._nested_node.getId()


cdef class Annotation:

    cdef CodeGeneratorRequest _root
    cdef _Annotation _annotation

    cdef Value _value

    def __cinit__(self, CodeGeneratorRequest root, object annotation):
        self._root = root
        self._annotation = deref(<_Annotation*>PyCapsule_GetPointer(annotation, NULL))

        self._value = None

    def _asdict(self):
        return {
            'id': self.id,
            'value': self.value._asdict(),
        }

    @property
    def id(self):
        return self._annotation.getId()

    @property
    def value(self):
        cdef _Value _value
        if self._value is None and self._annotation.hasValue():
            _value = self._annotation.getValue()
            self._value = Value(self._root, PyCapsule_New(&_value, NULL, NULL))
        return self._value


cdef class Field:

    cdef CodeGeneratorRequest _root
    cdef _Field _field

    cdef str _name
    cdef Type _type

    def __cinit__(self, CodeGeneratorRequest root, object field):
        self._root = root
        self._field = deref(<_Field*>PyCapsule_GetPointer(field, NULL))

        self._name = None
        self._type = None

    def _asdict(self):
        data = {
            'name': self.name,
            'code_order': self.code_order,
        }
        if self.is_slot():
            data['type'] = self.type._asdict()
        elif self.is_group():
            data['type_id'] = self.type_id
        return data

    @property
    def name(self):
        cdef bytes name_bytes
        if self._name is None and self._field.hasName():
            name_bytes = <bytes>self._field.getName()
            self._name = name_bytes.decode('utf8')
        return self._name

    @property
    def code_order(self):
        return self._field.getCodeOrder()

    def is_slot(self):
        return self._field.isSlot()

    @property
    def type(self):
        cdef _Type _type
        if self._field.isSlot() and self._field.getSlot().hasType():
            _type = self._field.getSlot().getType()
            self._type = Type(self._root, PyCapsule_New(&_type, NULL, NULL))
        return self._type

    def is_group(self):
        return self._field.isGroup()

    @property
    def type_id(self):
        if self._field.isGroup():
            return self._field.getGroup().getTypeId()
        else:
            return None


cdef class Enumerant:

    cdef CodeGeneratorRequest _root
    cdef _Enumerant _enumerant

    cdef str _name

    def __cinit__(self, CodeGeneratorRequest root, object enumerant):
        self._root = root
        self._enumerant = deref(<_Enumerant*>PyCapsule_GetPointer(enumerant, NULL))

        self._name = None

    def _asdict(self):
        return {
            'name': self.name,
            'code_order': self.code_order,
        }

    @property
    def name(self):
        cdef bytes name_bytes
        if self._name is None and self._enumerant.hasName():
            name_bytes = <bytes>self._enumerant.getName()
            self._name = name_bytes.decode('utf8')
        return self._name

    @property
    def code_order(self):
        return self._enumerant.getCodeOrder()


cdef class Const:

    cdef CodeGeneratorRequest _root
    cdef _Const _const

    cdef Type _type
    cdef Value _value

    def __cinit__(self, CodeGeneratorRequest root, object const):
        self._root = root
        self._const = deref(<_Const*>PyCapsule_GetPointer(const, NULL))

        self._type = None
        self._value = None

    def _asdict(self):
        return {
            'type': self.type._asdict(),
            'value': self.value._asdict(),
        }

    @property
    def type(self):
        cdef _Type _type
        if self._type is None and self._const.hasType():
            _type = self._const.getType()
            self._type = Type(self._root, PyCapsule_New(&_type, NULL, NULL))
        return self._type

    @property
    def value(self):
        cdef _Value _value
        if self._value is None and self._const.hasValue():
            _value = self._const.getValue()
            self._value = Value(self._root, PyCapsule_New(&_value, NULL, NULL))
        return self._value


cdef class Type:

    cdef CodeGeneratorRequest _root
    cdef _Type _type

    cdef Type _element_type

    def __cinit__(self, CodeGeneratorRequest root, object type):
        self._root = root
        self._type = deref(<_Type*>PyCapsule_GetPointer(type, NULL))

        self._element_type = None

    def _asdict(self):
        data = {}
        if self._type.isList():
            data['element_type'] = self.element_type._asdict()
        elif self._type.isEnum():
            data['type_id'] = self.type_id
        elif self._type.isStruct():
            data['type_id'] = self.type_id
        # Do not handle AnyPointer at the moment.
        return data

    def is_void(self):
        return self._type.isVoid()

    def is_primitive(self):
        return (
            self._type.isBool() or

            self._type.isInt8() or
            self._type.isInt16() or
            self._type.isInt32() or
            self._type.isInt64() or

            self._type.isUint8() or
            self._type.isUint16() or
            self._type.isUint32() or
            self._type.isUint64() or

            self._type.isFloat32() or
            self._type.isFloat64()
        )

    @property
    def primitive_type_name(self):

        if self._type.isBool():
            return 'bool'

        elif self._type.isInt8():
            return 'int8_t'
        elif self._type.isInt16():
            return 'int16_t'
        elif self._type.isInt32():
            return 'int32_t'
        elif self._type.isInt64():
            return 'int64_t'

        elif self._type.isUint8():
            return 'uint8_t'
        elif self._type.isUint16():
            return 'uint16_t'
        elif self._type.isUint32():
            return 'uint32_t'
        elif self._type.isUint64():
            return 'uint64_t'

        elif self._type.isFloat32():
            return 'float'
        elif self._type.isFloat64():
            return 'double'

        else:
            return None

    def is_text(self):
        return self._type.isText()

    def is_data(self):
        return self._type.isData()

    def is_list(self):
        return self._type.isList()

    @property
    def element_type(self):
        cdef _Type _element_type
        if self._element_type is None and self._type.isList() and self._type.hasElementType():
            _element_type = self._type.getElementType()
            self._element_type = Type(self._root, PyCapsule_New(&_element_type, NULL, NULL))
        return self._element_type

    def is_enum(self):
        return self._type.isEnum()

    def is_struct(self):
        return self._type.isStruct()

    @property
    def type_id(self):
        if self._type.isEnum():
            return self._type.getEnumTypeId()
        elif self._type.isStruct():
            return self._type.getStructTypeId()
        else:
            return None


cdef class Value:

    cdef CodeGeneratorRequest _root
    cdef _Value _value

    cdef _text

    def __cinit__(self, CodeGeneratorRequest root, object value):
        self._root = root
        self._value = deref(<_Value*>PyCapsule_GetPointer(value, NULL))

        self._text = None

    def _asdict(self):
        data = {}
        if self._value.isText():
            data['text'] = self.text
        return data

    def is_text(self):
        return self._value.isText()

    @property
    def text(self):
        cdef bytes text_bytes
        if self._text is None and self._value.isText() and self._value.hasText():
            text_bytes = <bytes>self._value.getText()
            self._text = text_bytes.decode('utf8')
        return self._text


cdef class RequestedFile:

    cdef CodeGeneratorRequest _root
    cdef _RequestedFile _requested_file

    cdef str _filename
    cdef tuple _imports

    def __cinit__(self, CodeGeneratorRequest root, object requested_file):
        self._root = root
        self._requested_file = deref(<_RequestedFile*>PyCapsule_GetPointer(requested_file, NULL))

        self._filename = None
        self._imports = None

    def _asdict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'imports': [
                import_._asdict()
                for import_ in self.imports or ()
            ],
        }

    @property
    def id(self):
        return self._requested_file.getId()

    @property
    def filename(self):
        cdef bytes filename_bytes
        if self._filename is None and self._requested_file.hasFilename():
            filename_bytes = <bytes>self._requested_file.getFilename()
            self._filename = filename_bytes.decode('utf8')
        return self._filename

    @property
    def imports(self):
        if self._imports is None and self._requested_file.hasImports():
            self._imports = self._get_imports()
        return self._imports

    def _get_imports(self):
        cdef List_Import _imports = self._requested_file.getImports()
        cdef Iterator_Import begin = _imports.begin()
        cdef Iterator_Import end = _imports.end()
        cdef _Import _import
        imports = []
        while begin != end:
            _import = deref(begin)
            imports.append(Import(self._root, PyCapsule_New(&_import, NULL, NULL)))
            inc(begin)
        return tuple(imports)


cdef class Import:

    cdef CodeGeneratorRequest _root
    cdef _Import _import

    cdef str _name

    def __cinit__(self, CodeGeneratorRequest root, object import_):
        self._root = root
        self._import = deref(<_Import*>PyCapsule_GetPointer(import_, NULL))

        self._name = None

    def _asdict(self):
        return {
            'name': self.name,
        }

    @property
    def id(self):
        return self._import.getId()

    @property
    def name(self):
        cdef bytes name_bytes
        if self._name is None and self._import.hasName():
            name_bytes = <bytes>self._import.getName()
            self._name = name_bytes.decode('utf8')
        return self._name
