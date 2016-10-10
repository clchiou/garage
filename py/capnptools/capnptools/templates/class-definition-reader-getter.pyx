<%page args="member"/>\
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
##      Enum
        % elif member.is_enum:
        return ${member.type_name}(<int>self._data.${member.getter}())
##      List or struct
        % elif member.is_list or member.is_struct:
        cdef ${member.cython_type_name}__Reader value
        if self._cache_${member.name} is None:
            value = self._data.${member.getter}()
            self._cache_${member.name} = ${member.type_name}(self._resource, PyCapsule_New(&value, NULL, NULL))
        return self._cache_${member.name}
##      None above
        % else:
        raise AssertionError
        % endif
