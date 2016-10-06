# ${display_name}
cdef extern from '${cc_header}':
    cdef enum ${cython_classname} '${cc_classname}':
        % for member in enum_members:
        ${member}
        % endfor
