<%page args="member"/>\
##  Void
    % if member.is_void:
    @property
    def ${member.name}(self):
        return None
##  Group
    % elif member.is_group:
    @property
    def ${member.name}(self):
        if self._builder_${member.name} is None:
            self._init_${member.name}()
        return self._builder_${member.name}
##  Otherwise
    % else:
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
        cdef bytes value = self._data.${member.getter}().cStr()
        % if member.is_text:
        return value.decode('utf8')
        % else:
        return value
        % endif
##      Enum
        % elif member.is_enum:
        return ${member.type_name}(<int>self._data.${member.getter}())
##      List or struct
        % elif member.is_list or member.is_struct:
        if self._builder_${member.name} is None:
            raise AssertionError
        return self._builder_${member.name}
##      None above
        % else:
        raise AssertionError
        % endif
    % endif
