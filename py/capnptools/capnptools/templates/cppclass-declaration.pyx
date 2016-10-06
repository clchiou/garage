# ${display_name}
cdef extern from '${cc_header}':
    cdef cppclass ${cython_classname}__Reader '${cc_classname}::Reader':
        % for function in context.get('cc_reader_member_functions', ()):
        ${function.return_type} ${function.name}(${', '.join(function.parameters)}) ${function.suffix}
        % endfor
        % if not context.get('cc_reader_member_functions'):
        pass
        % endif
    cdef cppclass ${cython_classname}__Builder '${cc_classname}::Builder':
        % for function in context.get('cc_builder_member_functions', ()):
        ${function.return_type} ${function.name}(${', '.join(function.parameters)}) ${function.suffix}
        % endfor
        % if not context.get('cc_builder_member_functions'):
        pass
        % endif
