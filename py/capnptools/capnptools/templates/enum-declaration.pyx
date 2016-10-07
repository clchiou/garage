## Workaround C++ enum class by declaring its members as global const
## variables.
# ${display_name}
cdef extern from '${cc_header}':
    cdef cppclass ${cython_classname} '${cc_classname}':
        pass
    % for member in members:
    cdef const ${cython_classname} ${cython_classname}__${member} 'static_cast<int>(${cc_classname}::${member})'
    % endfor
