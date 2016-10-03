"""Hand-written minimum schema.capnp.c++ wrapper."""

__all__ = [
    'CodeGeneratorRequest',
]

from cpython.pycapsule cimport PyCapsule_New, PyCapsule_GetPointer
from cython.operator cimport dereference as deref, preincrement as inc
from libcpp cimport bool


cdef extern from 'schema.capnp.h' namespace 'capnp::schema':

    cdef cppclass _Import 'capnp::schema::CodeGeneratorRequest::RequestedFile::Import::Reader':
        bool hasName() except +
        const char* getName 'getName().cStr'() except +


cdef extern from 'capnp/list.h' namespace 'capnp':

    cdef cppclass Iterator_Import 'capnp::List<capnp::schema::CodeGeneratorRequest::RequestedFile::Import>::Reader::Iterator':
        bool operator!=(Iterator_Import&)
        Iterator_Import& operator++()
        _Import operator*()

    cdef cppclass List_Import 'capnp::List<capnp::schema::CodeGeneratorRequest::RequestedFile::Import>::Reader':
        Iterator_Import begin()
        Iterator_Import end()


cdef extern from 'schema.capnp.h' namespace 'capnp::schema':

    cdef cppclass _RequestedFile 'capnp::schema::CodeGeneratorRequest::RequestedFile::Reader':

        bool hasFilename() except +
        const char* getFilename 'getFilename().cStr'() except +

        bool hasImports() except +
        List_Import getImports() except +


cdef extern from 'capnp/list.h' namespace 'capnp':

    cdef cppclass Iterator_RequestedFile 'capnp::List<capnp::schema::CodeGeneratorRequest::RequestedFile>::Reader::Iterator':
        bool operator!=(Iterator_RequestedFile&)
        Iterator_RequestedFile& operator++()
        _RequestedFile operator*()

    cdef cppclass List_RequestedFile 'capnp::List<capnp::schema::CodeGeneratorRequest::RequestedFile>::Reader':
        Iterator_RequestedFile begin()
        Iterator_RequestedFile end()


cdef extern from 'schema.capnp.h' namespace 'capnp::schema':

    cdef cppclass _CodeGeneratorRequest 'capnp::schema::CodeGeneratorRequest::Reader':
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

    cdef tuple _requested_files

    def __cinit__(self, bytes request_bytes):

        self._request_bytes = request_bytes

        cdef const char* request_begin = request_bytes
        self._reader = new FlatArrayMessageReader(ArrayPtr(
            <word*>request_begin,
            len(request_bytes),
        ))

        self._request = self._reader.getRoot()

        self._requested_files = None

    def __dealloc__(self):
        del self._reader

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

    @property
    def name(self):
        cdef bytes name_bytes
        if self._name is None and self._import.hasName():
            name_bytes = <bytes>self._import.getName()
            self._name = name_bytes.decode('utf8')
        return self._name
