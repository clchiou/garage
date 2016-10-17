# ${display_name}
## At the moment, Cython does not accept 'const except +' in member
## function declaration, but since 'const' suffix doesn't really provide
## any value to Cython anyway, we just declare it as 'except +'.
cdef extern from '${cc_header}':
    cdef cppclass ${cython_classname}__Reader '${cc_classname}::Reader':
        kj__StringTree toString() except +
        % for function in context.get('cc_reader_member_functions', ()):
        ${function.return_type} ${function.name}(${', '.join(function.parameters)}) except +
        % endfor
    cdef cppclass ${cython_classname}__Builder '${cc_classname}::Builder':
        kj__StringTree toString() except +
        % for function in context.get('cc_builder_member_functions', ()):
        ${function.return_type} ${function.name}(${', '.join(function.parameters)}) except +
        % endfor
