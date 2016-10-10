    def _as_dict(self):
        data = OrderedDict()
        % for member in members:
##      Void
        % if member.is_void:
        if self.is_${member.name}():
            data['${member.name}'] = None
        % else:
        value = self.${member.name}
        if value is not None:
##          Primitive/text/data/enum
            % if member.is_primitive or member.is_text or member.is_data or member.is_enum:
            data['${member.name}'] = value
##          List or struct
            % elif member.is_list or member.is_struct:
            data['${member.name}'] = value._as_dict()
            % endif
        % endif
        % endfor
        return data
