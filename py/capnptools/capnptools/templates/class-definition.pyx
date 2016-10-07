# ${display_name}

cdef class ${python_classname}:

    cdef MessageReader _reader
    cdef ${cython_classname}__Reader _data
    % for member in members:
    % if member.is_text:
    cdef str _cache_${member.name}
    % elif member.is_data:
    cdef bytes _cache_${member.name}
    % elif member.is_list:
    cdef tuple _cache_${member.name}
    % elif member.is_struct:
    cdef ${member.type_name} _cache_${member.name}
    % endif
    % endfor

    def __cinit__(self, MessageReader reader, object data):
        self._reader = reader
        self._data = dereference(<${cython_classname}__Reader*>PyCapsule_GetPointer(data, NULL))
        % for member in members:
        % if member.is_text or member.is_data or member.is_list or member.is_struct:
        self._cache_${member.name} = None
        % endif
        % endfor
    % for member in members:
    % if member.izzer:

    def is_${member.name}(self):
        return self._data.${member.izzer}()
    % endif
    % if member.getter:

    @property
    def ${member.name}(self):
        % if member.izzer:
        if not self._data.${member.izzer}():
            return None
        % endif
        % if member.hazzer:
        if not self._data.${member.hazzer}():
            return None
        % endif
        % if member.is_primitive:
        return self._data.${member.getter}()
        % elif member.is_text or member.is_data:
        cdef bytes value
        if self._cache_${member.name} is None:
            value = <bytes>self._data.${member.getter}().cStr()
            % if member.is_text:
            self._cache_${member.name} = value.decode('utf8')
            % else:
            self._cache_${member.name} = value
            % endif
        return self._cache_${member.name}
        % elif member.is_list:
        return None  # List
        % elif member.is_enum:
        return ${member.type_name}(<int>self._data.${member.getter}())
        % elif member.is_struct:
        cdef ${member.cython_type_name}__Reader value
        if self._cache_${member.name} is None:
            value = self._data.${member.getter}()
            self._cache_${member.name} = ${member.type_name}(self._reader, PyCapsule_New(&value, NULL, NULL))
        return self._cache_${member.name}
        % else:
        raise AssertionError
        % endif
    % endif
    % endfor

cdef class ${python_classname}__Builder:

    def __cinit__(self):
        pass
