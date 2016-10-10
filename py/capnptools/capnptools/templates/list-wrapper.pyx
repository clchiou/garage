## Extension type cannot inherit from Python type; otherwise I would
## like to make it inherit from `collections.MutableSequence`.
cdef class _ext__${python_classname}__Builder:

    cdef MessageBuilder _builder
    cdef ${cython_classname}__Builder _data

    def __cinit__(self, MessageBuilder builder, object data):
        self._builder = builder
        self._data = dereference(<${cython_classname}__Builder*>PyCapsule_GetPointer(data, NULL))

    def _as_dict(self):
##      Sub-list or struct
        % if level > 1 or list_type.is_struct:
        return [self[i]._as_dict() for i in range(len(self))]
##      Else
        % else:
        return [self[i] for i in range(len(self))]
        % endif

    def _as_reader(self):
        cdef ${cython_classname}__Reader data = self._data.asReader()
        return ${python_classname}(self, PyCapsule_New(&data, NULL, NULL))

    def __len__(self):
        return self._data.size()

    def __getitem__(self, unsigned int index):
##      Sub-list or struct
        % if level > 1 or list_type.is_struct:
        cdef ${element_cython_classname}__Builder value = self._data[index]
        return ${element_python_classname}__Builder(self._builder, PyCapsule_New(&value, NULL, NULL))
##      Primitive
        % elif list_type.is_primitive:
        return self._data[index]
##      Text of data
        % elif list_type.is_text or list_type.is_data:
        cdef bytes value = self._data[index].cStr()
        % if list_type.is_text:
        return value.decode('utf8')
        % else:
        return value
        % endif
##      Enum
        % elif list_type.is_enum:
        return ${element_python_classname}(<int>self._data[index])
##      None above
        % else:
        raise AssertionError
        % endif
    % if level > 1:

    def _init(self, unsigned int index, unsigned int size):
        cdef ${element_cython_classname}__Builder value = self._data.init(index. size)
        return ${element_python_classname}__Builder(self._builder, PyCapsule_New(&value, NULL, NULL))
    % elif list_type.is_text:

    def _init(self, unsigned int index, str value):
        cdef bytes bytes_value = value.encode('utf8')
        cdef const char* _value = bytes_value
        cdef size_t i = 0, size = len(bytes_value)
        cdef capnp__Text__Builder builder = self._data.init(index, size)
##      Can we use memcpy here?
        while i < size:
            builder[i] = _value[i]
            i += 1
        return value
    % elif list_type.is_data:

    def _init(self, unsigned int index, bytes value):
        cdef const char* _value = value
        cdef size_t i = 0, size = len(value)
        cdef capnp__Data__Builder builder = self._data.init(index, size)
##      Can we use memcpy here?
        while i < size:
            builder[i] = _value[i]
            i += 1
        return value
    % endif

    def __setitem__(self, unsigned int index, value):
##      Sub-list
        % if level > 1:
        cdef _ext__${element_python_classname}__Builder builder_value = value
        self._data.set(index, builder_value._data)
##      Struct
        % elif list_type.is_struct:
        raise IndexError('It is unsafe to set elements of struct list')
##      Primitive
        % elif list_type.is_primitive:
        self._data.set(index, value)
##      Text
        % elif list_type.is_text:
        cdef str str_value = value
        self._init(index, str_value)
##      Data
        % elif list_type.is_data:
        cdef bytes bytes_value = value
        self._init(index, bytes_value)
##      Enum
        % elif list_type.is_enum:
        cdef int int_value = value
        self._data.set(index, <${element_cython_classname}>int_value)
##      None above
        % else:
        raise AssertionError
        % endif

    def __delitem__(self, unsigned int index):
        raise IndexError('size of capnp::List<...>::Builder is fixed')

    def insert(self, unsigned int index, value):
        raise IndexError('size of capnp::List<...>::Builder is fixed')

class ${python_classname}__Builder(_ext__${python_classname}__Builder, MutableSequence):
    pass

## Extension type cannot inherit from Python type; otherwise I would
## like to make it inherit from `collections.Sequence`.
cdef class _ext__${python_classname}:

    Builder = ${python_classname}__Builder

##  Hold a reference to the _resource to make sure that it is released
##  after this object (_resource could be either a MessageReader or a
##  builder object).
    cdef object _resource
    cdef ${cython_classname}__Reader _data

    def __cinit__(self, object resource, object data):
        self._resource = resource
        self._data = dereference(<${cython_classname}__Reader*>PyCapsule_GetPointer(data, NULL))

    def _as_dict(self):
##      Sub-list or struct
        % if level > 1 or list_type.is_struct:
        return [self[i]._as_dict() for i in range(len(self))]
##      Else
        % else:
        return [self[i] for i in range(len(self))]
        % endif

    def __len__(self):
        return self._data.size()

    def __getitem__(self, unsigned int index):
##      Sub-list or struct
        % if level > 1 or list_type.is_struct:
        cdef ${element_cython_classname}__Reader value = self._data[index]
        return ${element_python_classname}(self._resource, PyCapsule_New(&value, NULL, NULL))
##      Primitive
        % elif list_type.is_primitive:
        return self._data[index]
##      Text of data
        % elif list_type.is_text or list_type.is_data:
        cdef bytes value = self._data[index].cStr()
        % if list_type.is_text:
        return value.decode('utf8')
        % else:
        return value
        % endif
##      Enum
        % elif list_type.is_enum:
        return ${element_python_classname}(<int>self._data[index])
##      None above
        % else:
        raise AssertionError
        % endif

class ${python_classname}(_ext__${python_classname}, Sequence):
    pass
