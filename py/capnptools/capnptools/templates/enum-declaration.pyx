# ${display_name}
cdef extern from '${cc_header}':
    cdef enum ${context.get('py_namespace', '')}__${py_enum} '${context.get('cc_namespace', '')}::${cc_enum}':
        % for cc_member in cc_enum_members:
        ${cc_member}
        % endfor
