# ${display_name}

cdef class ${python_classname}__Builder:

    def __cinit__(self):
        pass

cdef class ${python_classname}:

    Builder = ${python_classname}__Builder

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

    def _asdict(self):
        data = OrderedDict()
        % for member in members:
##      Void
        % if member.is_void:
        if self.is_${member.name}():
            data['${member.name}'] = None
        % else:
        value = self.${member.name}
        if value is not None:
##      Primitive/text/data/enum
            % if member.is_primitive or member.is_text or member.is_data or member.is_enum:
            data['${member.name}'] = value
##      List
            % elif member.is_list:
            data['${member.name}'] = None  # List
##      Struct
            % elif member.is_struct:
            data['${member.name}'] = value._asdict()
            % endif
        % endif
        % endfor
        return data
##
##  Generate members
##
    % for member in members:
##
##  Generate `is_X()`
##
    % if member.izzer:

    def is_${member.name}(self):
        return self._data.${member.izzer}()
    % endif
##
##  Generate `property(X)`
##
    % if member.getter:

    @property
    def ${member.name}(self):
##      Check izzer
        % if member.izzer:
        if not self._data.${member.izzer}():
            return None
        % endif
##      Check hazzer
        % if member.hazzer:
        if not self._data.${member.hazzer}():
            return None
        % endif
##      Primitive
        % if member.is_primitive:
        return self._data.${member.getter}()
##      Text or data
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
##      List
        % elif member.is_list:
        return None  # List
##      Enum
        % elif member.is_enum:
        return ${member.type_name}(<int>self._data.${member.getter}())
##      Struct
        % elif member.is_struct:
        cdef ${member.cython_type_name}__Reader value
        if self._cache_${member.name} is None:
            value = self._data.${member.getter}()
            self._cache_${member.name} = ${member.type_name}(self._reader, PyCapsule_New(&value, NULL, NULL))
        return self._cache_${member.name}
##      None above
        % else:
        raise AssertionError
        % endif
    % endif
    % endfor
