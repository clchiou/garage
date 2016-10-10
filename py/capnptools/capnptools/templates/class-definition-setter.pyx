<%page args="member"/>\
    @${member.name}.setter
    def ${member.name}(self, object new_value):
##      Void
        % if member.is_void:
        self._data.${member.setter}()
##      Primitive
        % elif member.is_primitive:
        cdef ${member.cython_type_name} primitive_value = new_value
        self._data.${member.setter}(primitive_value)
##      Text
        % elif member.is_text:
        cdef str str_value = new_value
        cdef bytes bytes_value = str_value.encode('utf8')
        cdef capnp__Text__Reader _new_value = capnp__Text__Reader(bytes_value, len(bytes_value))
        self._data.${member.setter}(_new_value)
##      Data
        % elif member.is_data:
        cdef bytes bytes_value = new_value
        cdef capnp__Data__Reader _new_value = capnp__Data__Reader(bytes_value, len(bytes_value))
        self._data.${member.setter}(_new_value)
##      List
        % elif member.is_list:
        cdef _ext__${member.type_name} reader_value
        cdef _ext__${member.type_name}__Builder builder_value
        cdef ${member.cython_type_name}__Builder value
        if isinstance(new_value, _ext__${member.type_name}):
            reader_value = new_value
            self._data.${member.setter}(reader_value._data)
            value = self._data.${member.getter}()
            self._builder_${member.name} = ${member.type_name}__Builder(self._builder, PyCapsule_New(&value, NULL, NULL))
        elif isinstance(new_value, _ext__${member.type_name}__Builder):
            builder_value = new_value
            self._data.${member.setter}(builder_value._data.asReader())
            value = self._data.${member.getter}()
            self._builder_${member.name} = ${member.type_name}__Builder(self._builder, PyCapsule_New(&value, NULL, NULL))
        else:
            if not isinstance(new_value, Sequence):
                new_value = tuple(new_value)
            self._init_${member.name}(len(new_value))
            for index, element in enumerate(new_value):
                self._builder_${member.name}[index] = element
##      Enum
        % elif member.is_enum:
        enum_value = ${member.type_name}(new_value)
        cdef int int_enum_value = enum_value.value
        self._data.${member.setter}(<${member.cython_type_name}>int_enum_value)
##      Struct
        % elif member.is_struct:
        cdef ${member.type_name}__Builder builder_value = new_value
        self._data.${member.setter}(builder_value._data.asReader())
        cdef ${member.cython_type_name}__Builder value = self._data.${member.getter}()
        self._builder_${member.name} = ${member.type_name}__Builder(self._builder, PyCapsule_New(&value, NULL, NULL))
##      None above
        % else:
        raise AssertionError
        % endif
