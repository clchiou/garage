## Extension type cannot inherit from Python type; otherwise I would
## like to make it inherit from `collections.MutableSequence`.
cdef class _ext__${python_classname}__Builder:
    pass

class ${python_classname}__Builder(_ext__${python_classname}__Builder, MutableSequence):
    pass

## Extension type cannot inherit from Python type; otherwise I would
## like to make it inherit from `collections.Sequence`.
cdef class _ext__${python_classname}:

    Builder = ${python_classname}__Builder

    cdef MessageReader _reader
    cdef ${cython_classname}__Reader _data

    def __cinit__(self, MessageReader reader, object data):
        self._reader = reader
        self._data = dereference(<${cython_classname}__Reader*>PyCapsule_GetPointer(data, NULL))

    def _asdict(self):
##      Sub-list or Struct
        % if level > 1 or list_type.is_struct:
        return [self[i]._asdict() for i in range(len(self))]
##      Else
        % else:
        return [self[i] for i in range(len(self))]
        % endif

    def __len__(self):
        return self._data.size()

    def __getitem__(self, index):
##      Primitive
        % if list_type.is_primitive:
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
##      Sub-list or Struct
        % elif level > 1 or list_type.is_struct:
        cdef ${element_cython_classname}__Reader value = self._data[index]
        return ${element_python_classname}(self._reader, PyCapsule_New(&value, NULL, NULL))
##      None above
        % else:
        raise AssertionError
        % endif

class ${python_classname}(_ext__${python_classname}, Sequence):
    pass
