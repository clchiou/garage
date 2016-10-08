cdef extern from "<capnp/message.h>":
    cdef cppclass capnp__MessageReader 'capnp::MessageReader':
        % for node in struct_nodes:
        ${node_table.get_cython_classname(node.id)}__Reader getRoot_${node_table.get_cython_classname(node.id)} 'getRoot<${node_table.get_cc_classname(node.id)}>'() except +
        % endfor

cdef extern from "<capnp/serialize.h>":
    cdef cppclass capnp__FlatArrayMessageReader 'capnp::FlatArrayMessageReader':
        capnp__FlatArrayMessageReader(kj__ArrayPtr array) except +
    cdef cppclass capnp__StreamFdMessageReader 'capnp::StreamFdMessageReader':
        capnp__StreamFdMessageReader(int fd) except +

cdef class MessageReader:

    cdef capnp__MessageReader *_reader

    def __cinit__(self):
        self._reader = NULL

    cdef own_reader(self, capnp__MessageReader *reader):
        self._reader = reader

    def __dealloc__(self):
        if self._reader != NULL:
            del self._reader

    def get_root(self, message_type):
        if self._reader == NULL:
            raise RuntimeError('reader was not initialized')
        % for node in struct_nodes:
        cdef ${node_table.get_cython_classname(node.id)}__Reader ${node_table.get_cython_classname(node.id)}_value
        % endfor
        % for node in struct_nodes:
        if message_type is ${node_table.get_python_classname(node.id)}:
            ${node_table.get_cython_classname(node.id)}_value = self._reader.getRoot_${node_table.get_cython_classname(node.id)}()
            return ${node_table.get_python_classname(node.id)}(self, PyCapsule_New(&${node_table.get_cython_classname(node.id)}_value, NULL, NULL))
        % endfor
        raise TypeError('unknown message type: %r' % message_type)

cdef class FlatArrayMessageReader(MessageReader):

    cdef bytes _array

    def __cinit__(self, bytes array):
        self._array = array
        cdef const char* _array = self._array
        self.own_reader(<capnp__MessageReader*>new capnp__FlatArrayMessageReader(kj__ArrayPtr(<capnp__word*>_array, len(self._array))))

cdef class StreamFdMessageReader(MessageReader):

    def __cinit__(self, int fd):
        self.own_reader(<capnp__MessageReader*>new capnp__StreamFdMessageReader(fd))
