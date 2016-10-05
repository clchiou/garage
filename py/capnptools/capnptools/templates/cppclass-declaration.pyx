# ${display_name}
cdef extern from '${cc_header}':
    cdef cppclass ${context.get('py_namespace', '')}__${py_class}__Reader '${context.get('cc_namespace', '')}::${cc_class}::Reader':
        % for method in context.get('reader_methods', ['pass']):
        ${method}
        % endfor
    cdef cppclass ${context.get('py_namespace', '')}__${py_class}__Builder '${context.get('cc_namespace', '')}::${cc_class}::Builder':
        % for method in context.get('builder_methods', ['pass']):
        ${method}
        % endfor
