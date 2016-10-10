cdef extern from "<capnp/message.h>":
    cdef cppclass capnp__MessageBuilder 'capnp::MessageBuilder':
        % for node in struct_nodes:
        ${node_table.get_cython_classname(node.id)}__Builder initRoot_${node_table.get_cython_classname(node.id)} 'initRoot<${node_table.get_cc_classname(node.id)}>'() except +
        % endfor
    cdef cppclass capnp__MallocMessageBuilder 'capnp::MallocMessageBuilder':
        pass

cdef class MessageBuilder:

    cdef capnp__MessageBuilder *_builder

    def __cinit__(self):
        self._builder = NULL

    cdef share_with(self, capnp__MessageBuilder *builder):
        self._builder = builder

    def init_root(self, message_type):
        if self._builder == NULL:
            raise RuntimeError('builder was not initialized')
        % for node in struct_nodes:
        cdef ${node_table.get_cython_classname(node.id)}__Builder ${node_table.get_cython_classname(node.id)}_value
        % endfor
        % for node in struct_nodes:
        if message_type in (${node_table.get_python_classname(node.id)}, ${node_table.get_python_classname(node.id)}__Builder):
            ${node_table.get_cython_classname(node.id)}_value = self._builder.initRoot_${node_table.get_cython_classname(node.id)}()
            return ${node_table.get_python_classname(node.id)}__Builder(self, PyCapsule_New(&${node_table.get_cython_classname(node.id)}_value, NULL, NULL))
        % endfor
        raise TypeError('unknown message type: %r' % message_type)

cdef class MallocMessageBuilder(MessageBuilder):

    cdef capnp__MallocMessageBuilder _maloc_builder

    def __cinit__(self):
        self.share_with(<capnp__MessageBuilder*>&self._maloc_builder)
